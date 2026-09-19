# -*- coding: utf-8 -*-
"""Idempotent creation of dashboard Number Cards (standard Number Card records)."""
import frappe

CARDS = [
    ("MB Today Sales", "manase_butcher.dashboard.today_sales", "Sales Invoice", "Currency"),
    ("MB Today Purchases", "manase_butcher.dashboard.today_purchases", "Purchase Receipt", "Currency"),
    ("MB Today Expenses", "manase_butcher.dashboard.today_expenses", "Fish Expense", "Currency"),
    ("MB Today Gross Profit", "manase_butcher.dashboard.today_profit", "Sales Invoice", "Currency"),
    ("MB Fish Received KG", "manase_butcher.dashboard.today_received_kg", "Fish Receiving", "Float"),
    ("MB Fish Sold KG", "manase_butcher.dashboard.today_sold_kg", "Sales Invoice", "Float"),
    ("MB Fish Waste KG", "manase_butcher.dashboard.today_waste_kg", "Fish Waste Record", "Float"),
    ("MB Current Stock KG", "manase_butcher.dashboard.current_stock_kg", "Bin", "Float"),
    ("MB Customer Debt", "manase_butcher.dashboard.customer_debt", "Sales Invoice", "Currency"),
    ("MB Supplier Debt", "manase_butcher.dashboard.supplier_debt", "Purchase Invoice", "Currency"),
    ("MB Pending Mobile Orders", "manase_butcher.dashboard.pending_mobile_orders",
     "Customer Order", "Int"),
    ("MB Open Transfers", "manase_butcher.dashboard.open_transfers", "Fish Stock Transfer", "Int"),
]


def setup_number_cards():
    for label, function, doctype, _stat in CARDS:
        try:
            if frappe.db.exists("Number Card", label):
                continue
            doc = frappe.get_doc({
                "doctype": "Number Card",
                "label": label,
                "document_type": doctype,
                "type": "Custom",
                "method": function,
                "is_standard": 0,
                "show_percentage_stats": 0,
            })
            doc.flags.ignore_permissions = True
            doc.insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title=f"Number card {label} failed",
                             message=frappe.get_traceback())
    _link_cards_to_workspace()
    frappe.db.commit()


def _link_cards_to_workspace():
    ws_name = "MANASE BUTCHER"
    if not frappe.db.exists("Workspace", ws_name):
        return
    ws = frappe.get_doc("Workspace", ws_name)
    existing = {c.name for c in ws.number_cards} if ws.meta.has_field("number_cards") else set()
    changed = False
    for label, *_ in CARDS:
        if label not in existing:
            ws.append("number_cards", {"name": label})
            changed = True
    if changed:
        ws.flags.ignore_permissions = True
        ws.save(ignore_permissions=True)
