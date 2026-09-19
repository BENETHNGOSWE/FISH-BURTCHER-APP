# -*- coding: utf-8 -*-
"""Sales Invoice event hooks: stamp branch/KG consistency and audit metrics."""
import frappe
from frappe.utils import flt


def validate_branch_and_kg(doc, method=None):
    """Ensure every fish invoice line carries KG and a branch warehouse (Rule 1/2)."""
    kg = 0
    for row in doc.items:
        is_fish = frappe.db.get_value("Item", row.item_code, "mb_is_fish")
        if is_fish:
            if not row.mb_weight_kg:
                row.mb_weight_kg = flt(row.stock_qty or row.qty)
            kg += flt(row.mb_weight_kg)
            warehouse = row.warehouse or doc.set_warehouse
            if warehouse:
                branch = frappe.db.get_value("Warehouse", warehouse, "mb_branch")
                if not doc.mb_branch and branch:
                    doc.mb_branch = branch
    doc.mb_total_kg = flt(kg, 3)


def on_submit_metrics(doc, method=None):
    # denormalised Fish Batch sold KG is updated via standard Batch ledger; nothing extra needed.
    return


def on_cancel_metrics(doc, method=None):
    from manase_butcher.audit import log_action
    log_action("Sales Invoice", doc.name, "Cancel", branch=doc.mb_branch,
               reason=doc.get("remarks"))
