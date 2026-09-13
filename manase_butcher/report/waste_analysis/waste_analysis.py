# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Waste KG/value by category, branch, item and employee."""
import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    cond = ["w.docstatus=1", "w.approval_status='Approved'"]
    values = []
    if filters.get("from_date"):
        cond.append("w.posting_date >= %s"); values.append(filters["from_date"])
    if filters.get("to_date"):
        cond.append("w.posting_date <= %s"); values.append(filters["to_date"])
    if filters.get("branch"):
        cond.append("w.branch = %s"); values.append(filters["branch"])
    if filters.get("waste_category"):
        cond.append("w.waste_category = %s"); values.append(filters["waste_category"])
    item_join = ""
    if filters.get("item_code"):
        item_join = "JOIN `tabFish Waste Item` wi2 ON wi2.parent=w.name AND wi2.item=%s"
        values.insert(0, filters["item_code"])
    rows = frappe.db.sql(
        f"""SELECT w.name, w.posting_date, w.branch, w.waste_category, w.employee,
                   wi.item, wi.item_name, wi.qty_kg, wi.amount, wi.reason
            FROM `tabFish Waste Record` w
            JOIN `tabFish Waste Item` wi ON wi.parent=w.name
            {item_join}
            WHERE {' AND '.join(cond)}
            ORDER BY w.posting_date DESC""", tuple(values), as_dict=True)
    columns = [
        {"fieldname": "name", "label": "Waste Record", "fieldtype": "Link",
         "options": "Fish Waste Record", "width": 150},
        {"fieldname": "posting_date", "label": "Date", "fieldtype": "Date", "width": 95},
        {"fieldname": "branch", "label": "Branch", "fieldtype": "Link", "options": "Branch"},
        {"fieldname": "waste_category", "label": "Category", "fieldtype": "Data", "width": 140},
        {"fieldname": "item", "label": "Fish", "fieldtype": "Link", "options": "Item", "width": 200},
        {"fieldname": "qty_kg", "label": "Waste KG", "fieldtype": "Float", "precision": 3},
        {"fieldname": "amount", "label": "Value", "fieldtype": "Currency"},
        {"fieldname": "employee", "label": "Employee", "fieldtype": "Link", "options": "Employee"},
        {"fieldname": "reason", "label": "Reason", "fieldtype": "Data", "width": 220},
    ]
    data = [{"name": r.name, "posting_date": str(r.posting_date), "branch": r.branch,
             "waste_category": r.waste_category, "employee": r.employee, "item": r.item,
             "qty_kg": flt(r.qty_kg, 3), "amount": flt(r.amount), "reason": r.reason}
            for r in rows]
    return columns, data
