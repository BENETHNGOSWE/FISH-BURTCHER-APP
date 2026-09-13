# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""'Where Did The KG Go?' - reconstructed from the Stock Ledger Entry so it
always reconciles with ERPNext (Rule 10)."""
import frappe
from frappe.utils import flt, getdate, get_datetime


def _columns():
    return [
        {"fieldname": "item", "label": "Fish Item", "fieldtype": "Link", "options": "Item", "width": 220},
        {"fieldname": "opening_kg", "label": "Opening KG", "fieldtype": "Float", "precision": 3, "width": 110},
        {"fieldname": "purchases", "label": "Purchases KG", "fieldtype": "Float", "precision": 3, "width": 120},
        {"fieldname": "processing_in", "label": "Processing In KG", "fieldtype": "Float", "precision": 3, "width": 130},
        {"fieldname": "processing_out", "label": "Processing Output KG", "fieldtype": "Float", "precision": 3, "width": 140},
        {"fieldname": "transfers_in", "label": "Transfers In KG", "fieldtype": "Float", "precision": 3, "width": 130},
        {"fieldname": "transfers_out", "label": "Transfers Out KG", "fieldtype": "Float", "precision": 3, "width": 130},
        {"fieldname": "sales", "label": "Sales KG (-)", "fieldtype": "Float", "precision": 3, "width": 110},
        {"fieldname": "sales_returns", "label": "Returns KG", "fieldtype": "Float", "precision": 3, "width": 110},
        {"fieldname": "waste", "label": "Waste KG (-)", "fieldtype": "Float", "precision": 3, "width": 110},
        {"fieldname": "adjustments", "label": "Adjustments KG", "fieldtype": "Float", "precision": 3, "width": 130},
        {"fieldname": "closing_kg", "label": "Closing KG (calc)", "fieldtype": "Float", "precision": 3, "width": 130},
        {"fieldname": "ledger_closing_kg", "label": "Ledger Closing KG", "fieldtype": "Float", "precision": 3, "width": 140},
        {"fieldname": "difference", "label": "Difference", "fieldtype": "Float", "precision": 3, "width": 100},
    ]


def _warehouses(filters):
    if filters.get("warehouse"):
        return [filters["warehouse"]]
    wfilters = {}
    if filters.get("branch"):
        wfilters["custom_mb_branch"] = filters["branch"]
    warehouses = frappe.db.get_all("Warehouse", filters=wfilters, pluck="name")
    # exclude waste/transit from combined view unless explicit
    return warehouses


def _fish_items(filters):
    f = {"custom_mb_is_fish": 1, "disabled": 0}
    if filters.get("item_code"):
        return [filters["item_code"]]
    return frappe.db.get_all("Item", filters=f, pluck="name")


def execute(filters=None):
    filters = filters or {}
    from manase_butcher.stock_utils import movement_kg
    start = get_datetime(f"{getdate(filters.get('from_date') or getdate())} 00:00:00")
    end = get_datetime(f"{getdate(filters.get('to_date') or getdate())} 23:59:59")
    warehouses = _warehouses(filters)
    if not warehouses:
        return _columns(), []
    data = []
    for item in _fish_items(filters):
        # opening = last qty_after_transaction per warehouse before start
        opening_rows = frappe.db.sql(
            """SELECT warehouse, qty_after_transaction FROM `tabStock Ledger Entry` s
               WHERE item_code=%s AND warehouse IN %s AND posting_datetime < %s AND is_cancelled=0
                 AND (SELECT COUNT(*) FROM `tabStock Ledger Entry` s2
                      WHERE s2.item_code=s.item_code AND s2.warehouse=s.warehouse
                        AND s2.posting_datetime < %s
                        AND (s2.posting_datetime > s.posting_datetime
                             OR (s2.posting_datetime=s.posting_datetime AND s2.creation>s.creation))) = 0
            """, (item, tuple(warehouses), start, start))
        opening = sum(flt(r[1]) for r in opening_rows)
        mv = movement_kg(item, warehouses, start, end)
        closing_calc = (opening + mv["purchases"] + mv["processing_out"]
                        + mv["transfers_in"] + mv["sales_returns"] + mv["adjustments"]
                        + mv["material_receipt_other"]
                        - abs(mv["processing_in"]) - abs(mv["transfers_out"])
                        - abs(mv["sales"]) - abs(mv["waste"]))
        ledger_rows = frappe.db.sql(
            """SELECT warehouse, qty_after_transaction FROM `tabStock Ledger Entry` s
               WHERE item_code=%s AND warehouse IN %s AND posting_datetime <= %s AND is_cancelled=0
                 AND (SELECT COUNT(*) FROM `tabStock Ledger Entry` s2
                      WHERE s2.item_code=s.item_code AND s2.warehouse=s.warehouse
                        AND s2.posting_datetime <= %s
                        AND (s2.posting_datetime > s.posting_datetime
                             OR (s2.posting_datetime=s.posting_datetime AND s2.creation>s.creation))) = 0
            """, (item, tuple(warehouses), end, end))
        ledger_closing = sum(flt(r[1]) for r in ledger_rows)
        data.append({
            "item": item,
            "opening_kg": round(opening, 3),
            "purchases": round(mv["purchases"], 3),
            "processing_in": round(mv["processing_in"], 3),
            "processing_out": round(mv["processing_out"], 3),
            "transfers_in": round(mv["transfers_in"], 3),
            "transfers_out": round(mv["transfers_out"], 3),
            "sales": round(mv["sales"], 3),
            "sales_returns": round(mv["sales_returns"], 3),
            "waste": round(mv["waste"], 3),
            "adjustments": round(mv["adjustments"], 3),
            "closing_kg": round(closing_calc, 3),
            "ledger_closing_kg": round(ledger_closing, 3),
            "difference": round(closing_calc - ledger_closing, 3),
        })
    data = [d for d in data if any(abs(flt(d[k])) > 0.0005
            for k in d if k.endswith("_kg") or k in ("purchases",))]
    return _columns(), data
