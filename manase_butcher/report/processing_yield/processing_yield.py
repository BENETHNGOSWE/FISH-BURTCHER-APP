# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Yield % / waste % by fish, supplier, processor, batch and date."""
from frappe.utils import flt
import frappe


def execute(filters=None):
    filters = filters or {}
    cond = ["p.docstatus=1"]
    values = []
    if filters.get("from_date"):
        cond.append("p.posting_date >= %s"); values.append(filters["from_date"])
    if filters.get("to_date"):
        cond.append("p.posting_date <= %s"); values.append(filters["to_date"])
    if filters.get("employee"):
        cond.append("p.employee = %s"); values.append(filters["employee"])
    if filters.get("supplier"):
        cond.append("b.supplier = %s"); values.append(filters["supplier"])
    rows = frappe.db.sql(
        f"""SELECT p.name, p.posting_date, p.employee, p.fish_batch,
                   b.supplier, p.input_kg, p.sellable_output_kg, p.waste_kg,
                   p.yield_pct, p.waste_pct, p.processing_cost
            FROM `tabFish Processing` p
            LEFT JOIN `tabFish Batch` b ON b.name=p.fish_batch
            WHERE {' AND '.join(cond)}
            ORDER BY p.posting_date DESC""", tuple(values), as_dict=True)
    item_filter = filters.get("item_code")
    data = []
    for r in rows:
        if item_filter:
            items = frappe.db.get_all("Fish Processing Input",
                                      {"parent": r.name, "item": item_filter}, limit=1)
            if not items:
                continue
        data.append({
            "processing": r.name, "posting_date": str(r.posting_date),
            "employee": r.employee, "fish_batch": r.fish_batch,
            "supplier": r.supplier,
            "input_kg": flt(r.input_kg, 3),
            "sellable_kg": flt(r.sellable_output_kg, 3),
            "waste_kg": flt(r.waste_kg, 3),
            "yield_pct": flt(r.yield_pct, 2),
            "waste_pct": flt(r.waste_pct, 2),
            "processing_cost": flt(r.processing_cost, 2),
            "cost_per_kg": flt(r.processing_cost / r.input_kg, 2) if r.input_kg else 0,
        })
    columns = [
        {"fieldname": "processing", "label": "Processing", "fieldtype": "Link",
         "options": "Fish Processing", "width": 150},
        {"fieldname": "posting_date", "label": "Date", "fieldtype": "Date", "width": 100},
        {"fieldname": "supplier", "label": "Supplier", "fieldtype": "Link",
         "options": "Supplier", "width": 160},
        {"fieldname": "employee", "label": "Processor", "fieldtype": "Link",
         "options": "Employee", "width": 140},
        {"fieldname": "fish_batch", "label": "Batch", "fieldtype": "Link",
         "options": "Fish Batch", "width": 160},
        {"fieldname": "input_kg", "label": "Input KG", "fieldtype": "Float", "precision": 3},
        {"fieldname": "sellable_kg", "label": "Sellable KG", "fieldtype": "Float", "precision": 3},
        {"fieldname": "waste_kg", "label": "Waste KG", "fieldtype": "Float", "precision": 3},
        {"fieldname": "yield_pct", "label": "Yield %", "fieldtype": "Percent", "width": 90},
        {"fieldname": "waste_pct", "label": "Waste %", "fieldtype": "Percent", "width": 90},
        {"fieldname": "processing_cost", "label": "Processing Cost", "fieldtype": "Currency"},
        {"fieldname": "cost_per_kg", "label": "Cost/KG", "fieldtype": "Currency"},
    ]
    return columns, data
