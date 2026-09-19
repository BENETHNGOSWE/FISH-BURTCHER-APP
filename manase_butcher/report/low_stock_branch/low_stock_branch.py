# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Fish below minimum (reorder level) by branch, with suggested transfer KG."""
import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    cond = ["i.mb_is_fish=1", "i.disabled=0",
            "ir.warehouse_reorder_level IS NOT NULL", "ir.warehouse_reorder_level > 0"]
    vals = []
    if filters.get("branch"):
        cond.append("w.mb_branch=%s"); vals.append(filters["branch"])
    rows = frappe.db.sql(
        f"""SELECT w.mb_branch AS branch, b.warehouse, b.item_code,
                   i.item_name, ir.warehouse_reorder_level AS minimum,
                   ir.warehouse_reorder_qty AS maximum,
                   GREATEST(COALESCE(b.actual_qty,0)-COALESCE(b.reserved_qty,0)
                       -COALESCE(b.mb_custom_reserved_kg,0),0) AS available_kg,
                   COALESCE((SELECT COALESCE(SUM(b2.actual_qty),0) FROM tabBin b2
                      JOIN tabWarehouse w2 ON w2.name=b2.warehouse
                      WHERE b2.item_code=b.item_code AND w2.mb_warehouse_kind
                      IN ('Central Processed','Central Raw')),0) AS central_kg
            FROM tabBin b
            JOIN tabItem i ON i.name=b.item_code
            JOIN `tabItem Reorder` ir ON ir.parent=i.name AND ir.warehouse=b.warehouse
            LEFT JOIN tabWarehouse w ON w.name=b.warehouse
            WHERE {' AND '.join(cond)}
            HAVING available_kg <= minimum
            ORDER BY branch, i.item_name""", tuple(vals), as_dict=True)
    columns = [
        {"fieldname": "branch", "label": "Branch", "fieldtype": "Link", "options": "Branch", "width": 130},
        {"fieldname": "item_code", "label": "Fish", "fieldtype": "Link", "options": "Item", "width": 220},
        {"fieldname": "available_kg", "label": "Available KG", "fieldtype": "Float", "precision": 2},
        {"fieldname": "minimum", "label": "Minimum KG", "fieldtype": "Float", "precision": 2},
        {"fieldname": "maximum", "label": "Maximum KG", "fieldtype": "Float", "precision": 2},
        {"fieldname": "central_kg", "label": "Central KG", "fieldtype": "Float", "precision": 2},
        {"fieldname": "suggested_transfer_kg", "label": "Suggest Transfer KG",
         "fieldtype": "Float", "precision": 2},
    ]
    data = []
    for r in rows:
        d = dict(r)
        d["suggested_transfer_kg"] = max(0, flt(r.maximum or r.minimum) - flt(r.available_kg))
        data.append(d)
    return columns, data
