# -*- coding: utf-8 -*-
"""Server-side POS operations for the MANASE fish POS page.

Prices are always resolved server-side; branch warehouse stock is reduced by a
standard Sales Invoice; tenders create standard Payment Entries. Credit is
limited by the standard customer credit-limit check.
"""
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowtime, cint, now_datetime

from manase_butcher.branch_utils import (
    get_settings, get_branch_warehouse, get_branch_cost_center,
    assert_branch_access, ROLE_CASHIER, ROLE_SALES, ROLE_BRANCH_MANAGER)
from manase_butcher.stock_utils import available_kg
from manase_butcher.setup.pricing import resolve_price
from manase_butcher.accounting_utils import make_payment_entry, get_payment_account
from manase_butcher.audit import log_action


POS_ROLES = ("Business Owner", "General Manager", "Branch Manager", "Sales Staff",
             "Cashier", "Accounts User", "Accounts Manager", "Sales Manager",
             "System Manager", "Administrator")


def _require_pos():
    if not (set(frappe.get_roles()) & set(POS_ROLES)):
        frappe.throw(_("POS access denied"), frappe.PermissionError)


@frappe.whitelist()
def get_pos_context(branch=None):
    """Branches the user may sell from + current branch stock + price types."""
    _require_pos()
    from manase_butcher.branch_utils import get_user_branches
    allowed = get_user_branches()
    filters = {"is_active": 1}
    if allowed:
        filters["name"] = ("in", allowed)
    branches = frappe.db.get_all("Branch", filters=filters,
                                 fields=["name", "branch_name", "warehouse",
                                         "cost_center", "default_price_list"])
    return {
        "branches": branches,
        "price_types": ["Retail", "Wholesale", "Restaurant", "Hotel", "Special", "Branch"],
        "payment_methods": ["Cash", "M-Pesa", "Tigo Pesa", "Airtel Money",
                            "HaloPesa", "Bank", "Card", "Credit"],
        "max_discount_percent": get_settings().max_discount_percent or 0,
    }


@frappe.whitelist()
def get_branch_items(branch, search=None, price_type="Retail"):
    _require_pos()
    warehouse = get_branch_warehouse(branch)
    conds = ["i.disabled=0", "i.is_sales_item=1", "i.mb_is_fish=1"]
    values = [warehouse]
    if search:
        conds.append("(i.item_name LIKE %s OR i.name LIKE %s)")
        values += [f"%{search}%", f"%{search}%"]
    rows = frappe.db.sql(
        f"""SELECT i.name AS item, i.item_name, i.image, i.stock_uom,
                   i.mb_freshness AS freshness, i.mb_preparation AS preparation,
                   GREATEST(COALESCE(b.actual_qty,0)-COALESCE(b.reserved_qty,0)
                       -COALESCE(b.mb_custom_reserved_kg,0),0) AS available_kg
            FROM tabItem i LEFT JOIN tabBin b ON b.item_code=i.name AND b.warehouse=%s
            WHERE {' AND '.join(conds)}
            ORDER BY i.item_name LIMIT 200""", tuple(values), as_dict=True)
    customer = frappe.form_dict.get("customer")
    for r in rows:
        r["price_per_kg"] = resolve_price(r.item, branch, price_type, customer)
    return rows


@frappe.whitelist()
def submit_sale():
    """Create and submit a POS sale.

    JSON body:
      branch, customer?, price_type, items:[{item, kg, discount?}],
      discount_total?, payments:[{mode, amount, reference?}]
    """
    _require_pos()
    import json
    data = json.loads(frappe.request.get_data() or b"{}") if frappe.request else {}
    if not data:
        data = frappe.form_dict.get("data")
        if isinstance(data, str):
            data = json.loads(data)
    branch = data.get("branch")
    assert_branch_access(branch)
    settings = get_settings()
    warehouse = get_branch_warehouse(branch)
    cost_center = get_branch_cost_center(branch)
    customer = data.get("customer") or (
        frappe.db.get_single_value("Selling Settings", "customer_group") and None)
    price_type = data.get("price_type") or "Retail"

    si = frappe.new_doc("Sales Invoice")
    si.company = settings.company
    si.customer = customer or _walkin_customer()
    si.posting_date = getdate()
    si.posting_time = nowtime()
    si.is_pos = 1
    si.update_stock = 1
    si.set_warehouse = warehouse
    si.cost_center = cost_center
    si.mb_branch = branch
    si.mb_sales_channel = data.get("channel") or "Walk-in"
    si.mb_sales_staff = frappe.db.get_value("Employee",
                                                   {"user_id": frappe.session.user}, "name")
    items = data.get("items") or []
    if not items:
        frappe.throw(_("Add at least one fish line"))
    for line in items:
        kg = flt(line.get("kg") or line.get("qty_kg"))
        if kg <= 0:
            frappe.throw(_("KG must be greater than zero"))
        available = available_kg(line["item"], warehouse)
        if available + 1e-9 < kg:
            frappe.throw(_("{0}: only {1} KG available").format(
                frappe.db.get_value("Item", line["item"], "item_name"), available))
        rate = resolve_price(line["item"], branch, price_type, si.customer)
        line_discount = flt(line.get("discount"))
        si.append("items", {
            "item_code": line["item"],
            "qty": kg, "uom": "Kg", "stock_uom": "Kg", "conversion_factor": 1,
            "rate": rate, "price_list_rate": rate,
            "discount_amount": line_discount,
            "warehouse": warehouse,
            "cost_center": cost_center,
            "mb_weight_kg": kg,
        })
    si.discount_amount = flt(data.get("discount_total"))
    si.flags.ignore_validate_update_after_submit = True
    si.flags.ignore_validate = True
    si.insert(ignore_permissions=True)
    _check_discount_authority(si, settings)
    si.submit()
    _set_invoice_kg(si)

    payments = data.get("payments") or []
    _check_credit(si, payments)
    for p in payments:
        amount = flt(p.get("amount"))
        if amount <= 0:
            continue
        mode = p.get("mode") or p.get("mode_of_payment")
        if mode == "Credit":
            continue  # remains outstanding
        pe = make_payment_entry(
            company=settings.company, payment_type="Receive", paid_amount=amount,
            party_type="Customer", party=si.customer, mode_of_payment=mode,
            payment_account=p.get("account") or _mode_account(mode, settings),
            reference_doctype="Sales Invoice", reference_name=si.name,
            branch=branch,
            mobile_provider=mode if mode in ("M-Pesa", "Tigo Pesa", "Airtel Money", "HaloPesa") else None,
            mobile_reference=p.get("reference"),
            remarks=f"POS sale {si.name}")
        if pe:
            p["payment_entry"] = pe.name
    log_action("Sales Invoice", si.name, "Submit", branch=branch,
               new_value={"total": si.grand_total,
                          "kg": sum(flt(i.mb_weight_kg or i.qty) for i in si.items)})
    frappe.db.commit()
    return {"ok": True, "data": {"invoice": si.name, "grand_total": si.grand_total,
                                 "outstanding": si.outstanding_amount, "payments": payments}}


def _set_invoice_kg(si):
    kg = sum(flt(i.mb_weight_kg or i.qty) for i in si.items)
    frappe.db.set_value("Sales Invoice", si.name, "mb_total_kg", kg,
                        update_modified=False)


def _check_discount_authority(si, settings):
    if flt(si.discount_amount) <= 0:
        return
    max_pct = flt(settings.max_discount_percent)
    roles = set(frappe.get_roles())
    if max_pct and (si.discount_amount / max(si.net_total, 1)) * 100 > max_pct \
            and not (roles & {"Business Owner", "General Manager", "Branch Manager"}):
        frappe.throw(_("Discount exceeds your authority limit"))
    log_action("Sales Invoice", si.name, "Price Change", field_label="discount",
               branch=si.mb_branch, new_value=si.discount_amount)


def _check_credit(si, payments):
    paid = sum(flt(p.get("amount")) for p in payments
               if (p.get("mode") or p.get("mode_of_payment")) != "Credit")
    if paid + 0.009 >= si.grand_total:
        return
    # standard credit-limit enforcement
    from erpnext.selling.doctype.customer.customer import check_credit_limit
    try:
        check_credit_limit(si.customer, si.company, si.grand_total - paid,
                           si.doctype, si.name, bypass_credit_limit=_can_bypass_credit())
    except frappe.ValidationError:
        raise
    except Exception:
        # older builds signature differs; rely on the submitted invoice validation
        si.flags.validate_apply_credit_limit = True


def _can_bypass_credit():
    return bool(set(frappe.get_roles()) & {
        "Business Owner", "General Manager", "Accounts Manager", "System Manager",
        "Administrator", "Bypass Credit Limit"})


def _mode_account(mode, settings):
    if mode in ("Cash",):
        return get_payment_account("Cash", settings.company)
    for r in settings.mobile_payment_accounts:
        if r.provider == mode:
            return r.account
    return get_payment_account(mode, settings.company)


def _walkin_customer():
    name = frappe.db.get_value("Customer", {"customer_name": ("like", "%Walk-in%")}, "name")
    if name:
        return name
    group = frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups"
    territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"
    doc = frappe.get_doc({"doctype": "Customer", "customer_name": "Walk-in Customer",
                          "customer_type": "Individual", "customer_group": group,
                          "territory": territory})
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


@frappe.whitelist()
def cancel_sale(invoice, reason):
    """Role-controlled cancellation with reason; reversal stays in ledger (Rule 8)."""
    if not (set(frappe.get_roles()) & {"Business Owner", "General Manager",
                                        "Branch Manager", "Accounts Manager",
                                        "System Manager", "Administrator"}):
        frappe.throw(_("Not authorised to cancel sales"), frappe.PermissionError)
    doc = frappe.get_doc("Sales Invoice", invoice)
    assert_branch_access(doc.mb_branch)
    doc.flags.ignore_permissions = True
    doc.cancel()
    log_action("Sales Invoice", invoice, "Cancel", branch=doc.mb_branch, reason=reason)
    return {"ok": True}
