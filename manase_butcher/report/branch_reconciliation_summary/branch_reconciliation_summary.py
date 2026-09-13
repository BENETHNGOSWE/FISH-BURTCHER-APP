# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Branch stock reconciliation summary: expected vs physical vs variance."""
import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    cond = ["r.docstatus=1"]
    vals = []
    if filters.get("from_date"):
        cond.append("r.posting_date>=%s"); vals.append(filters["from_date"])
    if filters.get("to_date"):
        cond.append("r.posting_date<=%s"); vals.append(filters["to_date"])
    if filters.get("branch"):
        cond.append("r.branch=%s"); vals.append(filters["branch"])
    rows = frappe.db.sql(
        f"""SELECT r.name, r.posting_date, r.branch, r.approval_status,
                   ri.item, ri.item_name, ri.expected_kg, ri.physical_kg,
                   ri.variance_kg, ri.variance_value, ri.reason
            FROM `tabBranch Stock Reconciliation` r
            JOIN `tabReconciliation Count Item` ri ON ri.parent=r.name
            WHERE {' AND '.join(cond)}
            ORDER BY r.posting_date DESC, r.branch""", tuple(vals), as_dict=True)
    columns = [
        {"fieldname": "name", "label": "Reconciliation", "fieldtype": "Link",
         "options": "Branch Stock Reconciliation", "width": 170},
        {"fieldname": "posting_date", "label": "Date", "fieldtype": "Date", "width": 95},
        {"fieldname": "branch", "label": "Branch", "fieldtype": "Link", "options": "Branch", "width": 120},
        {"fieldname": "approval_status", "label": "Status", "fieldtype": "Data", "width": 110},
        {"fieldname": "item", "label": "Fish", "fieldtype": "Link", "options": "Item", "width": 200},
        {"fieldname": "expected_kg", "label": "Expected KG", "fieldtype": "Float", "precision": 3},
        {"fieldname": "physical_kg", "label": "Physical KG", "fieldtype": "Float", "precision": 3},
        {"fieldname": "variance_kg", "label": "Variance KG", "fieldtype": "Float", "precision": 3},
        {"fieldname": "variance_value", "label": "Variance Value", "fieldtype": "Currency"},
        {"fieldname": "reason", "label": "Reason", "fieldtype": "Data", "width": 220},
    ]
    data = [{"name": r.name, "posting_date": str(r.posting_date), "branch": r.branch,
             "approval_status": r.approval_status, "item": r.item,
             "expected_kg": flt(r.expected_kg, 3), "physical_kg": flt(r.physical_kg, 3),
             "variance_kg": flt(r.variance_kg, 3), "variance_value": flt(r.variance_value),
             "reason": r.reason} for r in rows]
    return columns, data
