# -*- coding: utf-8 -*-
"""Fallback reservation ledger used when ERPNext Stock Reservation Entry
is unavailable in the running build. The preferred path is always standard SRE.
"""
import frappe
from frappe.utils import flt, now_datetime


def append_custom_reservation(sales_order, customer, branch, warehouse, item, kg,
                              expires_at=None, customer_order=None):
    kg = flt(kg)
    doc = frappe.new_doc("Stock Reservation")
    doc.customer_order = customer_order
    doc.customer = customer
    doc.branch = branch
    doc.warehouse = warehouse
    doc.item = item
    doc.reserved_kg = kg
    doc.status = "Reserved"
    doc.sales_order = sales_order
    doc.created_from = "Checkout"
    doc.expires_at = expires_at
    doc.flags.ignore_permissions = True
    doc.insert()
    doc.submit()
    _adjust_bin_reserved(item, warehouse, kg)
    return doc.name


def _adjust_bin_reserved(item, warehouse, delta):
    try:
        bin_name = frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse})
        if not bin_name:
            return
        current = flt(frappe.db.get_value("Bin", bin_name, "custom_mb_custom_reserved_kg"))
        frappe.db.set_value("Bin", bin_name, "custom_mb_custom_reserved_kg",
                            max(0, current + flt(delta)), update_modified=False)
    except Exception:
        frappe.log_error(title="Custom reservation bin update failed",
                         message=frappe.get_traceback())


def release_custom(name):
    doc = frappe.get_doc("Stock Reservation", name)
    if doc.status != "Reserved":
        return
    doc.status = "Released"
    if doc.docstatus == 1:
        doc.cancel()
    else:
        doc.save(ignore_permissions=True)
    _adjust_bin_reserved(doc.item, doc.warehouse, -flt(doc.reserved_kg))


def consume_custom(customer_order, warehouse=None):
    for name in frappe.db.get_all("Stock Reservation",
                                  {"customer_order": customer_order, "status": "Reserved"},
                                  pluck="name"):
        doc = frappe.get_doc("Stock Reservation", name)
        doc.status = "Consumed"
        doc.save(ignore_permissions=True)
        _adjust_bin_reserved(doc.item, warehouse or doc.warehouse, -flt(doc.reserved_kg))
