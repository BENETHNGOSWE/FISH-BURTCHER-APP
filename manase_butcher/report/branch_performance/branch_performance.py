# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Branch performance: sales, KG sold, waste, COGS, GP, expenses, net profit.

Money figures are read from the standard GL; KG comes from invoices / waste docs.
"""
import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    start = filters.get("from_date")
    end = filters.get("to_date")
    branch_filter = filters.get("branch")
    branches = [branch_filter] if branch_filter else frappe.db.get_all(
        "Branch", {"is_active": 1}, pluck="name")
    data = []
    for branch in branches:
        cc = frappe.db.get_value("Branch", branch, "cost_center")
        row = {"branch": branch}
        row["sales"] = _scalar(
            """SELECT COALESCE(SUM(si.base_net_amount),0) FROM `tabSales Invoice` si
               WHERE si.mb_branch=%s AND si.docstatus=1 AND si.is_return=0
                 AND (%(s)s IS NULL OR si.posting_date >= %(s)s)
                 AND (%(e)s IS NULL OR si.posting_date <= %(e)s)""",
            (branch,), {"s": start, "e": end})
        row["kg_sold"] = _scalar(
            """SELECT COALESCE(SUM(sii.mb_weight_kg), SUM(sii.stock_qty),0)
               FROM `tabSales Invoice Item` sii JOIN `tabSales Invoice` si ON si.name=sii.parent
               WHERE si.mb_branch=%s AND si.docstatus=1 AND si.is_return=0
                 AND (%(s)s IS NULL OR si.posting_date >= %(s)s)
                 AND (%(e)s IS NULL OR si.posting_date <= %(e)s)""",
            (branch,), {"s": start, "e": end})
        row["waste_kg"] = _scalar(
            """SELECT COALESCE(SUM(wi.qty_kg),0) FROM `tabFish Waste Item` wi
               JOIN `tabFish Waste Record` w ON w.name=wi.parent
               WHERE w.branch=%s AND w.docstatus=1
                 AND (%(s)s IS NULL OR w.posting_date >= %(s)s)
                 AND (%(e)s IS NULL OR w.posting_date <= %(e)s)""",
            (branch,), {"s": start, "e": end})
        row["cogs"], row["expenses"] = _gl(cc, start, end)
        row["gross_profit"] = flt(row["sales"]) - flt(row["cogs"])
        row["net_profit"] = flt(row["gross_profit"]) - flt(row["expenses"])
        row["receivables"] = flt(frappe.db.sql(
            "SELECT COALESCE(SUM(outstanding_amount),0) FROM `tabSales Invoice` "
            "WHERE mb_branch=%s AND docstatus=1", branch)[0][0])
        data.append(row)
    columns = [
        {"fieldname": "branch", "label": "Branch", "fieldtype": "Link", "options": "Branch", "width": 150},
        {"fieldname": "sales", "label": "Sales", "fieldtype": "Currency", "width": 140},
        {"fieldname": "kg_sold", "label": "KG Sold", "fieldtype": "Float", "precision": 2, "width": 100},
        {"fieldname": "waste_kg", "label": "Waste KG", "fieldtype": "Float", "precision": 2, "width": 100},
        {"fieldname": "cogs", "label": "COGS", "fieldtype": "Currency", "width": 130},
        {"fieldname": "gross_profit", "label": "Gross Profit", "fieldtype": "Currency", "width": 130},
        {"fieldname": "expenses", "label": "Expenses", "fieldtype": "Currency", "width": 120},
        {"fieldname": "net_profit", "label": "Net Profit", "fieldtype": "Currency", "width": 130},
        {"fieldname": "receivables", "label": "Customer Debt", "fieldtype": "Currency", "width": 130},
    ]
    return columns, data


def _scalar(query, args, named=None):
    if "%(s)s" in query:
        return flt(frappe.db.sql(query, args, named)[0][0])
    return flt(frappe.db.sql(query, args)[0][0])


def _gl(cost_center, start, end):
    if not cost_center:
        return 0, 0
    datecond = ""
    vals = {"cc": cost_center}
    if start:
        datecond += " AND gle.posting_date >= %(s)s"; vals["s"] = start
    if end:
        datecond += " AND gle.posting_date <= %(e)s"; vals["e"] = end
    row = frappe.db.sql(
        f"""SELECT
             COALESCE(SUM(CASE WHEN a.root_type='Expense' AND (a.account_name LIKE %s
                OR a.account_type='Cost of Goods Sold')
                THEN gle.debit-gle.credit ELSE 0 END),0) AS cogs,
             COALESCE(SUM(CASE WHEN a.root_type='Expense' AND IFNULL(a.account_type,'') <> 'Cost of Goods Sold'
                AND a.account_name NOT LIKE %s
                THEN gle.debit-gle.credit ELSE 0 END),0) AS expenses
             FROM `tabGL Entry` gle JOIN tabAccount a ON a.name=gle.account
             WHERE gle.cost_center=%(cc)s AND gle.is_cancelled=0 {datecond}""",
        ("%Cost of Goods Sold%", "%Cost of Goods Sold%",), vals, as_dict=True)[0]
    return flt(row.cogs), flt(row.expenses)
