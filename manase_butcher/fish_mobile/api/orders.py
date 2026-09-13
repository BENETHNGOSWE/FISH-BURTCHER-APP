# -*- coding: utf-8 -*-
"""Customer orders: cart validation, checkout/reservation, lifecycle, history."""
import json
import frappe
from frappe.utils import flt, cint, get_datetime, now_datetime

from ._helpers import begin, param, json_param, rate_limit
from manase_butcher.branch_utils import get_settings, get_branch_warehouse
from manase_butcher.accounting_utils import make_payment_entry


# ------------------------------------------------------------ payloads
def order_payload(name):
    o = frappe.get_doc("Customer Order", name)
    return {
        "name": o.name, "status": o.status, "order_type": o.order_type,
        "branch": o.branch, "warehouse": o.warehouse,
        "total_kg": flt(o.total_qty_kg, 3),
        "subtotal": flt(o.subtotal, 2), "discount": flt(o.discount_total or 0, 2),
        "delivery_fee": flt(o.delivery_fee or 0, 2),
        "total": flt(o.grand_total, 2), "paid": flt(o.paid_amount, 2),
        "outstanding": flt(o.outstanding_amount, 2),
        "payment_status": o.payment_status,
        "sales_order": o.sales_order, "sales_invoice": o.sales_invoice,
        "scheduled_time": str(o.scheduled_time or ""),
        "address": o.delivery_address_display or "",
        "items": [{"item": i.item, "name": i.item_name, "kg": flt(i.qty_kg, 3),
                    "rate": flt(i.rate), "amount": flt(i.amount),
                    "instructions": i.special_instructions} for i in o.items],
        "payments": [{"provider": p.provider, "amount": flt(p.amount),
                      "reference": p.reference, "status": p.status} for p in o.payments],
        "timestamps": {"confirmed_at": str(o.confirmed_at or ""),
                       "ready_at": str(o.ready_at or ""),
                       "delivered_at": str(o.delivered_at or "")},
    }


def _build_order_doc(customer, data):
    settings = get_settings()
    branch = data.get("branch")
    if not frappe.db.exists("Branch", {"name": branch, "is_active": 1}):
        frappe.throw("Select an active branch")
    warehouse = get_branch_warehouse(branch)
    order_type = data.get("order_type", "Pickup")
    if order_type not in ("Pickup", "Delivery"):
        frappe.throw("order_type must be Pickup or Delivery")
    doc = frappe.new_doc("Customer Order")
    doc.customer = customer
    doc.customer_name = frappe.db.get_value("Customer", customer, "customer_name")
    doc.phone = frappe.db.get_value("Customer", customer, "mobile_no")
    doc.branch = branch
    doc.warehouse = warehouse
    doc.order_type = order_type
    doc.created_from = "Mobile"
    doc.placed_by = customer
    doc.status = "Draft"
    if data.get("scheduled_time"):
        doc.scheduled_time = get_datetime(data["scheduled_time"])
    if order_type == "Delivery":
        doc.delivery_address = data.get("delivery_address")
        doc.delivery_address_display = data.get("address_text")
        doc.latitude = flt(data.get("latitude"))
        doc.longitude = flt(data.get("longitude"))
        doc.delivery_fee = flt(data.get("delivery_fee")) or settings.default_delivery_fee
        if data.get("delivery_address"):
            _assert_owns_address(customer, doc.delivery_address)
    if data.get("discount_total"):
        doc.discount_total = flt(data.get("discount_total"))
    lines = data.get("lines") or data.get("items") or []
    if not lines:
        frappe.throw("Cart is empty")
    for line in lines:
        doc.append("items", {
            "item": line.get("item"),
            "qty_kg": flt(line.get("kg") or line.get("qty_kg")),
            "special_instructions": line.get("instructions"),
        })
    return doc


def _assert_owns_address(customer, address):
    linked = frappe.db.exists("Dynamic Link",
                              {"parenttype": "Address", "parent": address,
                               "link_doctype": "Customer", "link_docname": customer})
    if not linked:
        frappe.throw("Address not found", frappe.PermissionError)


# ------------------------------------------------------------ cart (no write)
@frappe.whitelist()
def validate_cart():
    customer, sess = begin()
    rate_limit(f"cart:{customer}", 60, 60)
    data = json_param("data") or {
        "branch": param("branch"),
        "order_type": param("order_type") or "Pickup",
        "lines": json_param("lines") or json_param("items") or [],
        "delivery_fee": param("delivery_fee"),
    }
    doc = _build_order_doc(customer, data)
    doc.price_and_check_availability()
    return {"ok": True, "data": {
        "total_kg": doc.total_qty_kg,
        "subtotal": flt(doc.subtotal, 2),
        "delivery_fee": flt(doc.delivery_fee or 0, 2),
        "total": flt(doc.grand_total, 2),
        "lines": [{"item": i.item, "name": i.item_name, "kg": flt(i.qty_kg, 3),
                   "price_per_kg": flt(i.rate), "amount": flt(i.amount)} for i in doc.items],
    }}


# ------------------------------------------------------------ checkout
@frappe.whitelist()
def create_order():
    customer, sess = begin()
    rate_limit(f"order-create:{customer}", 15, 600)
    data = json_param("data") or {
        "branch": param("branch"), "order_type": param("order_type"),
        "lines": json_param("lines") or json_param("items") or [],
        "delivery_address": param("delivery_address"),
        "address_text": param("address_text"),
        "scheduled_time": param("scheduled_time"),
        "payment": json_param("payment") or {},
    }
    idem = frappe.request.headers.get("X-Idempotency-Key") if frappe.request else None
    if idem:
        cached = frappe.cache().get_value(f"mb-idem:{customer}:{idem}")
        if cached:
            return {"ok": True, "data": order_payload(cached), "idempotent": True}
    doc = _build_order_doc(customer, data)
    doc.price_and_check_availability()  # atomic KG check; throws on oversell
    doc.flags.ignore_permissions = True
    doc.insert()
    doc.reserve_stock()                 # Sales Order + SRE / fallback reservation
    doc.status = "Pending"
    payment = data.get("payment") or {}
    if payment.get("provider") and payment.get("reference"):
        doc.append("payments", {
            "provider": payment["provider"],
            "mode_of_payment": payment.get("mode_of_payment") or payment["provider"],
            "amount": flt(payment.get("amount")) or doc.grand_total,
            "reference": payment["reference"],
            "status": "Pending",
        })
    doc.status = "Pending"
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    doc.notify_branch()
    if idem:
        frappe.cache().set_value(f"mb-idem:{customer}:{idem}", doc.name, expires_in_sec=86400)
    return {"ok": True, "data": order_payload(doc.name)}


# ------------------------------------------------------------ reads
@frappe.whitelist()
def list_orders():
    customer, sess = begin()
    limit = min(cint(param("limit") or 20), 100)
    names = frappe.db.get_all("Customer Order",
                              filters={"customer": customer, "docstatus": ["<", 2]},
                              fields=["name", "status", "grand_total", "total_qty_kg",
                                      "creation", "order_type"],
                              order_by="creation desc", limit=limit)
    return {"ok": True, "data": names}


@frappe.whitelist()
def get_order():
    customer, sess = begin()
    name = param("id") or param("name")
    _own_order(customer, name)
    return {"ok": True, "data": order_payload(name)}


@frappe.whitelist()
def order_status():
    customer, sess = begin()
    name = param("id") or param("name")
    _own_order(customer, name)
    return {"ok": True, "data": {"name": name,
                                  "status": frappe.db.get_value("Customer Order", name, "status")}}


# ------------------------------------------------------------ customer actions
@frappe.whitelist()
def cancel_order():
    customer, sess = begin()
    name = param("id") or param("name")
    _own_order(customer, name)
    reason = param("reason") or "Cancelled by customer"
    doc = frappe.get_doc("Customer Order", name)
    if doc.status not in ("Pending", "Confirmed"):
        frappe.throw("Order can no longer be cancelled")
    frappe.local.flags.in_mobile_api = True
    doc.transition("Cancelled", reason=reason)
    return {"ok": True, "data": order_payload(name)}


@frappe.whitelist()
def add_payment():
    customer, sess = begin()
    name = param("id") or param("name")
    _own_order(customer, name)
    provider, reference, amount = param("provider"), param("reference"), flt(param("amount"))
    if not reference:
        frappe.throw("Provider reference required")
    if frappe.db.exists("Customer Order Payment",
                        {"parent": name, "reference": reference}):
        frappe.throw("Payment reference already used")
    doc = frappe.get_doc("Customer Order", name)
    doc.append("payments", {"provider": provider, "mode_of_payment": provider,
                            "amount": amount or doc.grand_total, "reference": reference,
                            "status": "Pending"})
    doc.save(ignore_permissions=True)
    return {"ok": True, "data": order_payload(name)}


def _own_order(customer, name):
    if not frappe.db.exists("Customer Order", {"name": name, "customer": customer}):
        frappe.throw("Order not found", frappe.PermissionError)


# ------------------------------------------------------------ staff-facing helper
def confirm_payment(order_name, provider, reference, amount, create_pe=True):
    """Called by provider callback or branch: mark payment confirmed; create PE."""
    from manase_butcher.accounting_utils import get_payment_account
    settings = get_settings()
    doc = frappe.get_doc("Customer Order", order_name)
    row = None
    for p in doc.payments:
        if p.reference == reference:
            row = p
            break
    if not row:
        row = doc.append("payments", {"provider": provider, "mode_of_payment": provider,
                                      "amount": amount, "reference": reference})
    row.status = "Confirmed"
    account = None
    for m in settings.mobile_payment_accounts:
        if m.provider == provider:
            account = m.account
    pe = None
    if create_pe:
        reference_dt, reference_name = None, None
        if doc.sales_invoice:
            reference_dt, reference_name = "Sales Invoice", doc.sales_invoice
        pe = make_payment_entry(
            company=settings.company, payment_type="Receive", paid_amount=flt(amount or row.amount),
            party_type="Customer", party=doc.customer, mode_of_payment=provider,
            payment_account=account or get_payment_account(provider, settings.company),
            reference_doctype=reference_dt, reference_name=reference_name,
            branch=doc.branch, mobile_provider=provider, mobile_reference=reference,
            remarks=f"Mobile order {order_name}")
        if pe:
            row.payment_entry = pe.name
    doc.flags.ignore_permissions = True
    doc.save()
    return row
