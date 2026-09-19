# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Revenue, COGS (landed/processed valuation), gross and net profit."""
import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    start, end = filters.get("from_date"), filters.get("to_date")
    branches = [filters["branch"]] if filters.get("branch") else frappe.db.get_all(
        "Branch", pluck="name")
    data = []
    for branch in branches:
        cc = frappe.db.get_value("Branch", branch, "cost_center")
        revenue = _sum(
            """SELECT COALESCE(SUM(base_net_amount),0) FROM `tabSales Invoice`
               WHERE mb_branch=%s AND docstatus=1 AND is_return=0
               AND (%s IS NULL OR posting_date>=%s) AND (%s IS NULL OR posting_date<=%s)""",
            (branch, start, start, end, end))
        kg = _sum(
            """SELECT COALESCE(SUM(sii.mb_weight_kg),SUM(sii.stock_qty),0)
               FROM `tabSales Invoice Item` sii JOIN `tabSales Invoice` si ON si.name=sii.parent
               WHERE si.mb_branch=%s AND si.docstatus=1 AND si.is_return=0
               AND (%s IS NULL OR si.posting_date>=%s) AND (%s IS NULL OR si.posting_date<=%s)""",
            (branch, start, start, end, end))
        cogs = _cogs_from_sle(branch, start, end, filters.get("item_code"),
                              filters.get("sales_channel"))
        expenses = _expenses(cc, start, end)
        gp = revenue - cogs
        data.append({
            "branch": branch, "kg_sold": flt(kg, 3),
            "revenue": flt(revenue), "cogs": flt(cogs),
            "gross_profit": flt(gp),
            "gp_pct": round(100 * gp / revenue, 2) if revenue else 0,
            "expenses": flt(expenses),
            "net_profit": flt(gp - expenses),
        })
    columns = [
        {"fieldname": "branch", "label": "Branch", "fieldtype": "Link", "options": "Branch", "width": 140},
        {"fieldname": "kg_sold", "label": "KG Sold", "fieldtype": "Float", "precision": 2},
        {"fieldname": "revenue", "label": "Revenue", "fieldtype": "Currency"},
        {"fieldname": "cogs", "label": "COGS (landed+processing)", "fieldtype": "Currency", "width": 200},
        {"fieldname": "gross_profit", "label": "Gross Profit", "fieldtype": "Currency"},
        {"fieldname": "gp_pct", "label": "GP %", "fieldtype": "Percent", "width": 80},
        {"fieldname": "expenses", "label": "Operating Expenses", "fieldtype": "Currency", "width": 150},
        {"fieldname": "net_profit", "label": "Net Profit", "fieldtype": "Currency"},
    ]
    return columns, data


def _sum(query, args):
    return flt(frappe.db.sql(query, args)[0][0])


def _cogs_from_sle(branch, start, end, item, channel):
    warehouse = frappe.db.get_value("Branch", branch, "warehouse")
    if not warehouse:
        return 0
    cond = ["sle.warehouse=%s", "sle.voucher_type='Sales Invoice'", "sle.is_cancelled=0",
            "sle.actual_qty < 0", "si.is_return=0"]
    vals = [warehouse]
    if start: cond.append("sle.posting_date>=%s"); vals.append(start)
    if end: cond.append("sle.posting_date<=%s"); vals.append(end)
    if item: cond.append("sle.item_code=%s"); vals.append(item)
    if channel: cond.append("si.mb_sales_channel=%s"); vals.append(channel)
    row = frappe.db.sql(
        f"""SELECT COALESCE(SUM(ABS(sle.stock_value_difference)),0)
            FROM `tabStock Ledger Entry` sle
            JOIN `tabSales Invoice` si ON si.name=sle.voucher_no
            WHERE {' AND '.join(cond)}""", tuple(vals))
    return flt(row[0][0])


def _expenses(cost_center, start, end):
    if not cost_center:
        return 0
    cond = ["gle.cost_center=%s", "gle.is_cancelled=0"]
    vals = [cost_center]
    if start: cond.append("gle.posting_date>=%s"); vals.append(start)
    if end: cond.append("gle.posting_date<=%s"); vals.append(end)
    row = frappe.db.sql(
        f"""SELECT COALESCE(SUM(gle.debit-gle.credit),0) FROM `tabGL Entry` gle
            JOIN tabAccount a ON a.name=gle.account
            WHERE {' AND '.join(cond)} AND a.root_type='Expense'
              AND IFNULL(a.account_type,'') <> 'Cost of Goods Sold'
              AND a.account_name NOT LIKE %s""",
        tuple(vals + ["%Cost of Goods Sold%"]))
    return flt(row[0][0])
