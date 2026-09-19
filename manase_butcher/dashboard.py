# -*- coding: utf-8 -*-
"""Custom Number Card functions for the MANASE BUTCHER 'TODAY' dashboard.

Each whitelisted function returns a NumberCard-compatible value.
All figures read standard ERPNext ledger/transaction data.
"""
import frappe
from frappe.utils import flt, today


def _today():
    return today()


@frappe.whitelist()
def today_sales():
    v = flt(frappe.db.sql(
        "SELECT COALESCE(SUM(base_grand_total),0) FROM `tabSales Invoice` "
        "WHERE posting_date=%s AND docstatus=1 AND is_return=0", _today())[0][0])
    return {"value": v}


@frappe.whitelist()
def today_purchases():
    v = flt(frappe.db.sql(
        "SELECT COALESCE(SUM(base_grand_total),0) FROM `tabPurchase Receipt` "
        "WHERE posting_date=%s AND docstatus=1", _today())[0][0])
    return {"value": v}


@frappe.whitelist()
def today_expenses():
    v = flt(frappe.db.sql(
        "SELECT COALESCE(SUM(amount),0) FROM `tabFish Expense` "
        "WHERE posting_date=%s AND docstatus=1", _today())[0][0])
    return {"value": v}


@frappe.whitelist()
def today_profit():
    today = _today()
    revenue = flt(frappe.db.sql(
        "SELECT COALESCE(SUM(base_net_amount),0) FROM `tabSales Invoice` "
        "WHERE posting_date=%s AND docstatus=1 AND is_return=0", today)[0][0])
    cogs = flt(frappe.db.sql(
        """SELECT COALESCE(SUM(ABS(sle.stock_value_difference)),0)
           FROM `tabStock Ledger Entry` sle
           JOIN `tabSales Invoice` si ON si.name=sle.voucher_no
           WHERE si.posting_date=%s AND si.docstatus=1 AND si.is_return=0
             AND sle.voucher_type='Sales Invoice' AND sle.actual_qty < 0""", today)[0][0])
    return {"value": revenue - cogs}


@frappe.whitelist()
def today_received_kg():
    v = flt(frappe.db.get_value("Fish Receiving",
                               {"posting_date": _today(), "docstatus": 1},
                               "SUM(total_qty_kg)"))
    return {"value": v}


@frappe.whitelist()
def today_sold_kg():
    v = flt(frappe.db.sql(
        """SELECT COALESCE(SUM(sii.mb_weight_kg), SUM(sii.stock_qty),0)
           FROM `tabSales Invoice Item` sii JOIN `tabSales Invoice` si ON si.name=sii.parent
           WHERE si.posting_date=%s AND si.docstatus=1 AND si.is_return=0""", _today())[0][0])
    return {"value": v}


@frappe.whitelist()
def today_waste_kg():
    v = flt(frappe.db.get_value("Fish Waste Record",
                               {"posting_date": _today(), "docstatus": 1},
                               "SUM(total_kg)"))
    return {"value": v}


@frappe.whitelist()
def current_stock_kg():
    v = flt(frappe.db.sql(
        """SELECT COALESCE(SUM(b.actual_qty),0) FROM tabBin b
           JOIN tabItem i ON i.name=b.item_code
           WHERE i.mb_is_fish=1""")[0][0])
    return {"value": v}


@frappe.whitelist()
def customer_debt():
    v = flt(frappe.db.sql(
        "SELECT COALESCE(SUM(outstanding_amount),0) FROM `tabSales Invoice` "
        "WHERE docstatus=1 AND outstanding_amount>0")[0][0])
    return {"value": v}


@frappe.whitelist()
def supplier_debt():
    v = flt(frappe.db.sql(
        "SELECT COALESCE(SUM(outstanding_amount),0) FROM `tabPurchase Invoice` "
        "WHERE docstatus=1 AND outstanding_amount>0")[0][0])
    return {"value": v}


@frappe.whitelist()
def pending_mobile_orders():
    v = frappe.db.count("Customer Order",
                       {"status": ("in", ("Pending", "Confirmed", "Preparing", "Ready"))})
    return {"value": v}


@frappe.whitelist()
def open_transfers():
    v = frappe.db.count("Fish Stock Transfer",
                       {"status": ("in", ("Approved", "Dispatched")), "docstatus": 1})
    return {"value": v}
