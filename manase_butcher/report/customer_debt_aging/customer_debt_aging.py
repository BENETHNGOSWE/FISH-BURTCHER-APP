# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Customer debt aging buckets based on standard AR Sales Invoice data."""
import frappe
from frappe.utils import flt, today, date_diff


def execute(filters=None):
    filters = filters or {}
    cond = ["si.docstatus=1", "si.outstanding_amount > 0.009"]
    values = []
    if filters.get("customer"):
        cond.append("si.customer = %s"); values.append(filters["customer"])
    if filters.get("branch"):
        cond.append("si.mb_branch = %s"); values.append(filters["branch"])
    rows = frappe.db.sql(
        f"""SELECT si.customer, c.customer_name, c.mobile_no,
                   si.name AS invoice, si.posting_date, si.due_date,
                   si.outstanding_amount, si.mb_branch AS branch
            FROM `tabSales Invoice` si
            LEFT JOIN tabCustomer c ON c.name=si.customer
            WHERE {' AND '.join(cond)} ORDER BY si.customer, si.posting_date""",
        tuple(values), as_dict=True)
    data = {}
    now = today()
    for r in rows:
        d = data.setdefault(r.customer, {
            "customer": r.customer, "customer_name": r.customer_name,
            "mobile_no": r.mobile_no, "b0_7": 0, "b8_30": 0, "b31_60": 0,
            "b61_90": 0, "b90_plus": 0, "total": 0})
        age = date_diff(now, r.due_date or r.posting_date)
        if age <= 7: d["b0_7"] += flt(r.outstanding_amount)
        elif age <= 30: d["b8_30"] += flt(r.outstanding_amount)
        elif age <= 60: d["b31_60"] += flt(r.outstanding_amount)
        elif age <= 90: d["b61_90"] += flt(r.outstanding_amount)
        else: d["b90_plus"] += flt(r.outstanding_amount)
        d["total"] += flt(r.outstanding_amount)
    columns = [
        {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "customer_name", "label": "Name", "fieldtype": "Data", "width": 160},
        {"fieldname": "mobile_no", "label": "Phone", "fieldtype": "Data", "width": 130},
        {"fieldname": "b0_7", "label": "0-7 days", "fieldtype": "Currency"},
        {"fieldname": "b8_30", "label": "8-30 days", "fieldtype": "Currency"},
        {"fieldname": "b31_60", "label": "31-60 days", "fieldtype": "Currency"},
        {"fieldname": "b61_90", "label": "61-90 days", "fieldtype": "Currency"},
        {"fieldname": "b90_plus", "label": "90+ days", "fieldtype": "Currency"},
        {"fieldname": "total", "label": "Outstanding", "fieldtype": "Currency", "width": 130},
    ]
    return columns, sorted(data.values(), key=lambda x: -x["total"])
