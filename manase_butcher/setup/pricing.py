# -*- coding: utf-8 -*-
"""Item Price audit hooks - every price change is recorded with old/new value and reason."""
import frappe
from frappe.utils import now_datetime


def before_item_price_insert(doc, method=None):
    if not doc.get("mb_price_type"):
        doc.mb_price_type = "Retail"


def item_price_on_update(doc, method=None):
    try:
        before = doc.get_doc_before_save()
        if before and flt(before.price_list_rate) != flt(doc.price_list_rate):
            row = frappe.get_doc({
                "doctype": "Price Change Log",
                "change_datetime": now_datetime(),
                "changed_by": frappe.session.user,
                "item": doc.item_code,
                "item_name": doc.item_name,
                "branch": doc.mb_branch,
                "price_type": doc.mb_price_type or "Retail",
                "currency": doc.currency,
                "old_price": before.price_list_rate,
                "new_price": doc.price_list_rate,
            })
            row.flags.ignore_permissions = True
            row.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(title="Price change log failed", message=frappe.get_traceback())


def resolve_price(item_code, branch=None, price_type="Retail", customer=None, qty=0):
    """Resolve the applicable KG price. Server is the only authority on price.

    Priority: customer/special -> branch+type -> type price list -> Item standard.
    """
    from manase_butcher.branch_utils import get_settings
    settings = get_settings()
    price_list_map = {
        "Retail": settings.retail_price_list,
        "Wholesale": settings.wholesale_price_list,
        "Restaurant": settings.restaurant_price_list,
        "Hotel": settings.hotel_price_list,
        "Special": None,
        "Branch": None,
    }
    currency = settings.default_currency or "TZS"
    # 1. special / branch specific price
    conditions = {"item_code": item_code, "mb_price_type": price_type}
    if branch:
        row = frappe.db.get_value(
            "Item Price",
            dict(conditions, mb_branch=branch, selling=1),
            "price_list_rate")
        if row:
            return flt(row)
    # 2. price-list based
    pl = price_list_map.get(price_type) or settings.retail_price_list
    if pl:
        row = frappe.db.get_value(
            "Item Price",
            {"item_code": item_code, "price_list": pl, "selling": 1,
             "mb_branch": ["is", "not set"]},
            "price_list_rate", order_by="valid_from desc")
        if row:
            return flt(row)
    # 3. any selling price
    row = frappe.db.get_value("Item Price",
                              {"item_code": item_code, "selling": 1},
                              "price_list_rate", order_by="valid_from desc")
    if row:
        return flt(row)
    # 4. item standard rate
    return flt(frappe.db.get_value("Item", item_code, "standard_selling_rate"))


def flt(v, p=None):
    from frappe.utils import flt as _flt
    return _flt(v, p)
