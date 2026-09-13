# -*- coding: utf-8 -*-
"""Inventory scheduled jobs: low stock digest and high waste alerts."""
import frappe
from frappe.utils import flt, today, add_days


def low_stock_digest():
    """Notify branch managers / inventory manager of fish below reorder level."""
    rows = frappe.db.sql(
        """SELECT b.warehouse, w.custom_mb_branch AS branch, b.item_code,
                  i.item_name, GREATEST(COALESCE(b.actual_qty,0)-COALESCE(b.reserved_qty,0)
                     -COALESCE(b.custom_mb_custom_reserved_kg,0),0) AS available,
                  ir.warehouse_reorder_level AS minimum
           FROM tabBin b
           JOIN tabItem i ON i.name=b.item_code
           LEFT JOIN tabWarehouse w ON w.name=b.warehouse
           LEFT JOIN `tabItem Reorder` ir
                  ON ir.parent=i.name AND ir.warehouse=b.warehouse
           WHERE i.custom_mb_is_fish=1 AND i.disabled=0
             AND ir.warehouse_reorder_level IS NOT NULL
             AND (COALESCE(b.actual_qty,0)-COALESCE(b.reserved_qty,0)) <= ir.warehouse_reorder_level
        """, as_dict=True)
    if not rows:
        return
    by_branch = {}
    for r in rows:
        by_branch.setdefault(r.branch or "Central", []).append(r)
    notified = set()
    for branch, items in by_branch.items():
        users = []
        if branch and branch != "Central":
            manager = frappe.db.get_value("Branch", branch, "manager")
            if manager:
                users.append(manager)
        users += frappe.db.get_all("Has Role",
                                   filters={"role": ("in", ("Inventory Manager", "General Manager",
                                                             "Business Owner"))},
                                   pluck="parent")
        lines = "\n".join(f"- {x.item_name}: {flt(x.available):.1f} KG (min {flt(x.minimum):.1f})"
                          for x in items)
        msg = f"Low fish stock at {branch}:\n{lines}"
        for user in set(users):
            if user in notified:
                continue
            notified.add(user)
            try:
                frappe.publish_realtime("msgprint", msg, user=user)
            except Exception:
                pass
    return len(rows)


def high_waste_alert(threshold_pct=5.0):
    """Flag branches whose waste over the last day exceeds threshold % of sales KG."""
    since = add_days(today(), -1)
    branches = frappe.db.get_all("Branch", pluck="name")
    alerts = []
    for branch in branches:
        warehouse = frappe.db.get_value("Branch", branch, "warehouse")
        waste = flt(frappe.db.sql(
            """SELECT COALESCE(SUM(ABS(sle.actual_qty)),0)
               FROM `tabStock Ledger Entry` sle
               JOIN `tabStock Entry` se ON se.name=sle.voucher_no
               WHERE sle.warehouse=%s AND sle.is_cancelled=0
                 AND se.custom_mb_fish_waste_record IS NOT NULL
                 AND sle.posting_date >= %s""", (warehouse, since))[0][0])
        sold = flt(frappe.db.sql(
            """SELECT COALESCE(SUM(sii.custom_mb_weight_kg), SUM(sii.stock_qty),0)
               FROM `tabSales Invoice Item` sii
               JOIN `tabSales Invoice` si ON si.name=sii.parent
               WHERE si.custom_mb_branch=%s AND si.docstatus=1 AND si.posting_date>=%s
                 AND si.is_return=0""", (branch, since))[0][0])
        if sold > 0 and (waste / sold) * 100 >= threshold_pct:
            alerts.append((branch, waste, sold))
    for branch, waste, sold in alerts:
        for role in ("Business Owner", "General Manager", "Inventory Manager"):
            for user in frappe.db.get_all("Has Role", {"role": role}, pluck="parent"):
                try:
                    frappe.publish_realtime(
                        "msgprint",
                        f"HIGH WASTE: {branch} wasted {waste:.1f} KG vs {sold:.1f} KG sold "
                        f"({waste/sold*100:.1f}%) since {since}.",
                        user=user)
                except Exception:
                    pass
    return alerts
