# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Forward/backward trace for a Fish Batch: supplier -> receiving -> processing
-> transfers -> branches -> sales."""
import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    batch = filters.get("fish_batch")
    columns = [
        {"fieldname": "stage", "label": "Stage", "fieldtype": "Data", "width": 150},
        {"fieldname": "reference", "label": "Document", "fieldtype": "Data", "width": 200},
        {"fieldname": "branch", "label": "Branch", "fieldtype": "Link", "options": "Branch", "width": 130},
        {"fieldname": "item", "label": "Fish", "fieldtype": "Link", "options": "Item", "width": 200},
        {"fieldname": "kg", "label": "KG", "fieldtype": "Float", "precision": 3, "width": 100},
        {"fieldname": "date", "label": "Date", "fieldtype": "Date", "width": 100},
        {"fieldname": "note", "label": "Note", "fieldtype": "Data", "width": 200},
    ]
    if not batch:
        return columns, []
    b = frappe.db.get_value("Fish Batch", batch,
                            ["name", "supplier", "fish_receiving", "item", "received_kg",
                             "sellable_kg", "waste_kg", "received_date"], as_dict=True)
    if not b:
        return columns, []
    data = [
        {"stage": "Received", "reference": b.fish_receiving or b.name, "item": b.item,
         "kg": flt(b.received_kg, 3), "date": str(b.received_date or ""),
         "note": f"Supplier {b.supplier}"},
        {"stage": "Processed sellable", "reference": b.name, "item": b.item,
         "kg": flt(b.sellable_kg, 3)},
        {"stage": "Waste", "reference": b.name, "item": b.item, "kg": flt(b.waste_kg, 3)},
    ]
    # stock movements of the underlying ERPNext batch
    erp_batch = frappe.db.get_value("Fish Batch", batch, "erpnext_batch")
    if erp_batch:
        moves = frappe.db.sql(
            """SELECT sle.voucher_type, sle.voucher_no, sle.warehouse, sle.actual_qty,
                      sle.posting_date, w.mb_branch AS branch, sle.item_code
               FROM `tabStock Ledger Entry` sle
               LEFT JOIN tabWarehouse w ON w.name=sle.warehouse
               WHERE sle.batch_no=%s AND sle.is_cancelled=0
               ORDER BY sle.posting_datetime""", erp_batch, as_dict=True)
        for m in moves:
            data.append({
                "stage": m.voucher_type, "reference": m.voucher_no,
                "branch": m.branch, "item": m.item_code,
                "kg": flt(m.actual_qty, 3), "date": str(m.posting_date),
                "note": m.warehouse,
            })
    return columns, data
