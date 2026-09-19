# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Customer (mobile) order state machine wrapping standard Sales Order,
Stock Reservation Entry, Sales Invoice and Payment Entry.
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime, add_days, add_to_date, cint

from manase_butcher.audit import log_action
from manase_butcher.branch_utils import (
    get_settings, get_branch_warehouse, get_branch_cost_center, assert_branch_access,
)
from manase_butcher.stock_utils import available_kg, release_order_reservations
from manase_butcher.doctype_compat import append_custom_reservation
from manase_butcher.accounting_utils import make_payment_entry
from manase_butcher.notifications import notify_customer, notify_branch_users
from manase_butcher.setup.pricing import resolve_price

BRANCH_STAFF_ROLES = ("Business Owner", "General Manager", "Branch Manager",
                      "Sales Staff", "Cashier", "Delivery Staff", "System Manager",
                      "Stock Manager", "Administrator")


class CustomerOrder(Document):
    # ------------------------------------------------------------ validate
    def validate(self):
        settings = get_settings()
        self.company = settings.company
        if self.branch and not self.warehouse:
            self.warehouse = get_branch_warehouse(self.branch)
        self._totals()

    def _totals(self):
        if not self.items:
            return
        self.total_qty_kg = round(sum(flt(i.qty_kg) for i in self.items), 3)
        self.subtotal = round(sum(flt(i.qty_kg) * flt(i.rate) for i in self.items), 2)
        self.grand_total = flt(self.subtotal) - flt(self.discount_total or 0) + flt(self.delivery_fee or 0)
        self.paid_amount = round(sum(flt(p.amount) for p in self.payments
                                     if p.status == "Confirmed"), 2)
        self.outstanding_amount = flt(self.grand_total) - flt(self.paid_amount)
        self.payment_status = ("Paid" if self.outstanding_amount <= 0 else
                               ("Partly Paid" if self.paid_amount > 0 else "Unpaid"))

    # ------------------------------------------------------------ placement
    def price_and_check_availability(self, price_type="Retail", customer=None):
        """Server re-prices every line and checks KG availability (Rule 4)."""
        settings = get_settings()
        if len(self.items) > cint(settings.max_cart_lines or 40):
            frappe.throw(_("Too many lines in one order"))
        checks = []
        for line in self.items:
            if flt(line.qty_kg) <= 0:
                frappe.throw(_("Order weight must be greater than zero"))
            line.rate = resolve_price(line.item, self.branch, price_type, customer or self.customer)
            if not line.rate:
                frappe.throw(_("No selling price configured for {0}").format(line.item))
            line.amount = flt(line.qty_kg) * flt(line.rate)
            line.item_name = line.item_name or frappe.db.get_value("Item", line.item, "item_name")
            checks.append(line)
        self._totals()
        # availability under lock
        for line in checks:
            self._lock_bin(line.item, self.warehouse)
            avail = available_kg(line.item, self.warehouse)
            if avail + 1e-9 < flt(line.qty_kg):
                frappe.throw(_("{0}: only {1} KG available at {2}").format(
                    line.item_name or line.item, avail, self.branch),
                    title=_("Insufficient stock"))

    def _lock_bin(self, item, warehouse):
        frappe.db.sql(
            "SELECT * FROM tabBin WHERE item_code=%s AND warehouse=%s FOR UPDATE",
            (item, warehouse))

    def reserve_stock(self):
        """Create Sales Order + standard Stock Reservation Entries (KG)."""
        if self.sales_order:
            return self.sales_order
        settings = get_settings()
        so = frappe.new_doc("Sales Order")
        so.transaction_date = getdate()
        so.delivery_date = add_days(getdate(), 1)
        so.customer = self.customer
        so.customer_name = self.customer_name
        so.company = settings.company
        so.order_type = "Sales"
        so.set_warehouse = self.warehouse
        so.mb_branch = self.branch
        so.mb_sales_channel = "Mobile"
        so.mb_customer_order = self.name
        so.po_no = self.name
        for line in self.items:
            so.append("items", {
                "item_code": line.item,
                "item_name": line.item_name,
                "qty": flt(line.qty_kg),
                "uom": "Kg",
                "stock_uom": "Kg",
                "conversion_factor": 1,
                "rate": flt(line.rate),
                "price_list_rate": flt(line.rate),
                "warehouse": self.warehouse,
                "delivery_date": so.delivery_date,
            })
        so.flags.ignore_permissions = True
        so.insert()
        so.submit()
        self.db_set("sales_order", so.name)
        self._create_reservations(so)
        return so.name

    def _create_reservations(self, so):
        settings = get_settings()
        expires = add_minutes(now_datetime(), cint(settings.order_validity_minutes) or 20)
        reserved_any = False
        for so_item, line in zip(so.items, self.items):
            try:
                sre = frappe.new_doc("Stock Reservation Entry")
                sre.item_code = line.item
                sre.warehouse = self.warehouse
                sre.qty = flt(line.qty_kg)
                sre.stock_uom = "Kg"
                sre.from_voucher_type = "Sales Order"
                sre.voucher_no = so.name
                sre.voucher_detail_no = so_item.name
                sre.company = settings.company
                sre.posting_date = getdate()
                if sre.meta.has_field("mb_customer_order"):
                    sre.mb_customer_order = self.name
                sre.flags.ignore_permissions = True
                sre.insert()
                sre.submit()
                reserved_any = True
            except Exception:
                frappe.log_error(title="SRE failed, using custom reservation",
                                 message=frappe.get_traceback())
                append_custom_reservation(
                    sales_order=so.name, customer=self.customer, branch=self.branch,
                    warehouse=self.warehouse, item=line.item, kg=line.qty_kg,
                    expires_at=expires, customer_order=self.name)
        self.db_set("reservation_info",
                    "Reserved via Stock Reservation Entry" if reserved_any
                    else "Reserved via custom reservation ledger")

    # ------------------------------------------------------------ status machine
    VALID_TRANSITIONS = {
        "Pending": ("Confirmed", "Rejected", "Cancelled"),
        "Confirmed": ("Preparing", "Cancelled"),
        "Preparing": ("Ready",),
        "Ready": ("Collected", "Out for Delivery"),
        "Out for Delivery": ("Delivered",),
        "Delivered": ("Completed",),
        "Collected": ("Completed",),
    }

    def transition(self, new_status, reason=None, payment_lines=None):
        if new_status not in self.VALID_TRANSITIONS.get(self.status, ()):
            frappe.throw(_("Cannot move order from {0} to {1}").format(self.status, new_status))
        self._require_staff()
        if self.branch:
            assert_branch_access(self.branch)
        if new_status == "Rejected":
            self._release(reason or "Rejected by branch")
            self.status = "Rejected"
        elif new_status == "Cancelled":
            self._release(reason or "Cancelled")
            self.cancellation_reason = reason
            self.status = "Cancelled"
        else:
            self.status = new_status
            stamp = {
                "Confirmed": "confirmed_at",
                "Ready": "ready_at",
                "Delivered": "delivered_at",
            }.get(new_status)
            if stamp:
                self.set(stamp, now_datetime())
        if new_status in ("Delivered", "Collected"):
            self.complete(payment_lines)
        self.save()
        log_action("Customer Order", self.name, "Update", field_label="status",
                   old_value=self.status, new_value=new_status, branch=self.branch,
                   reason=reason)

    def _require_staff(self):
        if frappe.local.flags.in_mobile_api:
            return  # ownership enforced at API layer for customer-cancel only
        roles = set(frappe.get_roles())
        if not (roles & set(BRANCH_STAFF_ROLES)):
            frappe.throw(_("Not authorised for this order action"), frappe.PermissionError)

    # ------------------------------------------------------------ completion
    def complete(self, payment_lines=None):
        if self.sales_invoice:
            self.status = "Completed"
            return self.sales_invoice
        if not self.sales_order:
            self.reserve_stock()
        si = self._make_sales_invoice()
        self._record_payments(si)
        self.db_set("sales_invoice", si.name)
        self.db_set("status", "Completed")
        self.db_set("delivered_at", now_datetime())
        log_action("Customer Order", self.name, "Submit",
                   new_value={"invoice": si.name, "kg": self.total_qty_kg},
                   branch=self.branch)
        notify_customer(self.customer, "Order completed",
                        f"Thank you! Receipt {si.name} for {self.grand_total:,.0f} TZS.",
                        data={"doctype": "Customer Order", "name": self.name},
                        sms_fallback=True)
        return si.name

    def _make_sales_invoice(self):
        from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
        si = make_sales_invoice(self.sales_order)
        si.is_pos = 0
        si.update_stock = 1
        si.set_warehouse = self.warehouse
        si.mb_branch = self.branch
        si.mb_sales_channel = "Mobile"
        si.mb_customer_order = self.name
        si.mb_total_kg = self.total_qty_kg
        si.cost_center = get_branch_cost_center(self.branch)
        delivery_item = frappe.db.get_value("Item", {"item_name": "Delivery Fee"}, "name")
        if flt(self.delivery_fee) and delivery_item:
            si.append("items", {
                "item_code": delivery_item,
                "qty": 1, "uom": "Nos", "stock_uom": "Nos", "conversion_factor": 1,
                "rate": flt(self.delivery_fee), "income_account":
                    get_settings().delivery_income_account,
                "cost_center": get_branch_cost_center(self.branch),
            })
        si.flags.ignore_permissions = True
        si.insert()
        si.submit()
        return si

    def _record_payments(self, invoice):
        settings = get_settings()
        for p in self.payments:
            if p.status != "Confirmed" or p.payment_entry or flt(p.amount) <= 0:
                continue
            account = self._wallet_account(p.provider)
            pe = make_payment_entry(
                company=settings.company, payment_type="Receive",
                paid_amount=flt(p.amount), party_type="Customer", party=self.customer,
                mode_of_payment=p.mode_of_payment or p.provider, payment_account=account,
                reference_doctype="Sales Invoice", reference_name=invoice.name,
                branch=self.branch, mobile_provider=p.provider if p.provider != "Cash" else None,
                mobile_reference=p.reference, remarks=f"Mobile order {self.name}")
            if pe:
                p.db_set("payment_entry", pe.name)

    def _wallet_account(self, provider):
        for r in get_settings().mobile_payment_accounts:
            if r.provider == provider:
                return r.account
        return None

    def _release(self, reason):
        try:
            release_order_reservations(self.name)
        except Exception:
            frappe.log_error(title="Reservation release failed", message=frappe.get_traceback())
        if self.sales_order:
            so = frappe.get_doc("Sales Order", self.sales_order)
            if so.docstatus == 1:
                so.flags.ignore_permissions = True
                so.cancel()
        notify_customer(self.customer, "Order cancelled",
                        f"Order {self.name} was cancelled. {reason or ''}",
                        data={"doctype": "Customer Order", "name": self.name},
                        sms_fallback=True)

    # ------------------------------------------------------------ events
    def after_insert(self):
        # Customer Order is a stateful front document; the ledger lives on the
        # standard Sales Order / Sales Invoice / Payment Entry.
        pass

    def notify_branch(self):
        notify_branch_users(self.branch,
                            f"New mobile order {self.name}: {self.total_qty_kg} KG, "
                            f"{self.grand_total:,.0f} TZS ({self.order_type})",
                            "Customer Order", self.name)


# ------------------------------------------------------------ notifications event
def notify_on_status(doc, method=None):
    """doc_events hook: push FCM/SMS when status changes."""
    if not getattr(doc, "get_doc_before_save", None):
        return
    before = doc.get_doc_before_save()
    if not before or before.status == doc.status or not doc.customer:
        return
    messages = {
        "Confirmed": ("Order confirmed", "Your order has been accepted and is being prepared."),
        "Preparing": ("Preparing your fish", "Your fish is being prepared."),
        "Ready": ("Ready for collection", "Your order is ready."),
        "Out for Delivery": ("Out for delivery", "Your order is on its way."),
        "Delivered": ("Delivered", "Your order has been delivered. Enjoy!"),
        "Collected": ("Collected", "Your order has been collected. Enjoy!"),
        "Rejected": ("Order not accepted", "Your order could not be accepted and any payment will be refunded."),
    }
    if doc.status in messages:
        title, body = messages[doc.status]
        try:
            notify_customer(doc.customer, title, body,
                            data={"doctype": "Customer Order", "name": doc.name})
        except Exception:
            frappe.log_error(title="order notification failed", message=frappe.get_traceback())


# ------------------------------------------------------------ small helpers
def add_minutes(dt, n):
    return add_to_date(dt, minutes=n)
