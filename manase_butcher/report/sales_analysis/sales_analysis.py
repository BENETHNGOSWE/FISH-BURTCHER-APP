# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Fish sales analysis by day, branch, item, employee, customer and channel."""
import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    cond = ["si.docstatus=1", "si.is_return=0"]
    values = []
    for field, column in (("from_date", "si.posting_date >= %s"),
                          ("to_date", "si.posting_date <= %s"),
                          ("branch", "si.mb_branch = %s"),
                          ("sales_channel", "si.mb_sales_channel = %s"),
                          ("customer", "si.customer = %s"),
                          ("employee", "si.mb_sales_staff = %s")):
        if filters.get(field):
            cond.append(column); values.append(filters[field])
    item_join = ""
    if filters.get("item_code"):
        item_join = "JOIN `tabSales Invoice Item` sif ON sif.parent=si.name AND sif.item_code=%s"
        values.insert(0, filters["item_code"])
    rows = frappe.db.sql(
        f"""SELECT si.name, si.posting_date, si.mb_branch AS branch,
                   si.mb_sales_channel AS channel, si.customer,
                   si.mb_sales_staff AS employee,
                   sii.item_code, sii.item_name,
                   sii.mb_weight_kg AS kg, sii.stock_qty,
                   sii.net_amount, sii.discount_amount
            FROM `tabSales Invoice` si
            JOIN `tabSales Invoice Item` sii ON sii.parent=si.name
            {item_join}
            WHERE {' AND '.join(cond)}
            ORDER BY si.posting_date DESC, si.name""", tuple(values), as_dict=True)
    columns = [
        {"fieldname": "name", "label": "Invoice", "fieldtype": "Link",
         "options": "Sales Invoice", "width": 150},
        {"fieldname": "posting_date", "label": "Date", "fieldtype": "Date", "width": 95},
        {"fieldname": "branch", "label": "Branch", "fieldtype": "Link", "options": "Branch", "width": 120},
        {"fieldname": "channel", "label": "Channel", "fieldtype": "Data", "width": 100},
        {"fieldname": "customer", "label": "Customer", "fieldtype": "Link",
         "options": "Customer", "width": 160},
        {"fieldname": "employee", "label": "Sales Staff", "fieldtype": "Link",
         "options": "Employee", "width": 130},
        {"fieldname": "item_code", "label": "Fish", "fieldtype": "Link",
         "options": "Item", "width": 200},
        {"fieldname": "kg", "label": "KG", "fieldtype": "Float", "precision": 3, "width": 90},
        {"fieldname": "discount_amount", "label": "Discount", "fieldtype": "Currency", "width": 100},
        {"fieldname": "net_amount", "label": "Net Amount", "fieldtype": "Currency", "width": 120},
    ]
    data = []
    for r in rows:
        data.append({"name": r.name, "posting_date": str(r.posting_date), "branch": r.branch,
                     "channel": r.channel or "Walk-in", "customer": r.customer,
                     "employee": r.employee, "item_code": r.item_code,
                     "kg": flt(r.kg or r.stock_qty, 3),
                     "discount_amount": flt(r.discount_amount), "net_amount": flt(r.net_amount)})
    return columns, data
