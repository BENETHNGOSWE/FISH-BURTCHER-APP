# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Daily branch closing: ledger-derived expected takings per mode of payment,
manual counts, explained variance, cash over/short Journal Entry on approval.
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, get_datetime, now_datetime

from manase_butcher.audit import log_action
from manase_butcher.branch_utils import (
    get_settings, get_branch_warehouse, get_branch_cost_center)
from manase_butcher.accounting_utils import make_journal_entry


class DailyBranchClosing(Document):
    def validate(self):
        settings = get_settings()
        self.company = settings.company
        if self.branch and not self.warehouse:
            self.warehouse = get_branch_warehouse(self.branch)
        self._totals()
        if self.approval_status in ("Submitted", "Approved") and flt(self.total_variance) != 0:
            if not (self.explanation or "").strip():
                frappe.throw(_("Explanation is mandatory when there is a variance"))

    def _totals(self):
        self.expected_total = round(sum(flt(r.expected_amount) for r in self.payments), 2)
        self.actual_total = round(sum(
            flt(r.actual_amount) if r.actual_amount is not None and r.actual_amount != ""
            else flt(r.expected_amount) for r in self.payments), 2)
        self.total_variance = round(flt(self.actual_total) - flt(self.expected_total), 2)
        cash_row = next((r for r in self.payments if r.mode_of_payment == "Cash"), None)
        if cash_row:
            self.cash_expected = flt(cash_row.expected_amount)
            self.cash_actual = (flt(cash_row.actual_amount)
                                if cash_row.actual_amount not in (None, "") else self.cash_expected)
            self.cash_variance = flt(self.cash_actual) - flt(self.cash_expected)

    # ------------------------------------------------------------ fetch ledger
    @frappe.whitelist()
    def fetch_data(self):
        if self.docstatus == 1:
            frappe.throw(_("Cannot refetch a submitted closing"))
        day = getdate(self.posting_date)
        start, end = get_datetime(f"{day} 00:00:00"), get_datetime(f"{day} 23:59:59")
        invoices = frappe.db.sql(
            """SELECT name, grand_total, outstanding_amount FROM `tabSales Invoice`
               WHERE custom_mb_branch=%s AND posting_date=%s AND docstatus=1 AND is_return=0""",
            (self.branch, day), as_dict=True)
        self.invoice_count = len(invoices)
        self.sales_total = round(sum(flt(i.grand_total) for i in invoices), 2)
        self.credit_total = round(sum(flt(i.outstanding_amount) for i in invoices), 2)
        self.kg_sold = flt(frappe.db.sql(
            """SELECT COALESCE(SUM(sii.custom_mb_weight_kg), SUM(sii.stock_qty))
               FROM `tabSales Invoice Item` sii JOIN `tabSales Invoice` si ON si.name=sii.parent
               WHERE si.custom_mb_branch=%s AND si.posting_date=%s AND si.docstatus=1 AND si.is_return=0""",
            (self.branch, day))[0][0] or 0, 3)

        # payments grouped by mode
        pay_rows = frappe.db.sql(
            """SELECT pe.mode_of_payment, pe.custom_mb_mobile_provider AS provider,
                     SUM(pe.paid_amount) AS amount
               FROM `tabPayment Entry` pe
               WHERE pe.custom_mb_branch=%s AND pe.posting_date=%s AND pe.docstatus=1
                     AND pe.payment_type='Receive'
               GROUP BY pe.mode_of_payment, pe.custom_mb_mobile_provider""",
            (self.branch, day), as_dict=True)
        # invoices fully on credit (no payment) represented as Credit mode
        amounts = {(r.mode_of_payment, r.provider): flt(r.amount) for r in pay_rows}
        if flt(self.credit_total) > 0:
            amounts[("Credit", None)] = amounts.get(("Credit", None), 0) + flt(self.credit_total)
        self.set("payments", [])
        for (mode, provider), amount in sorted(amounts.items()):
            self.append("payments", {
                "mode_of_payment": mode,
                "provider": provider or mode,
                "expected_amount": round(amount, 2),
                "actual_amount": round(amount, 2),
            })
        if not self.payments:
            self.append("payments", {"mode_of_payment": "Cash", "provider": "Cash",
                                     "expected_amount": 0, "actual_amount": 0})
        self._stock_kg(start)
        self._totals()
        self.save()
        return True

    def _stock_kg(self, start):
        if not self.warehouse:
            return
        self.closing_stock_kg = flt(frappe.db.sql(
            """SELECT COALESCE(SUM(actual_qty),0) FROM tabBin
               WHERE warehouse=%s AND item_code IN (
                   SELECT name FROM tabItem WHERE custom_mb_is_fish=1)""",
            self.warehouse)[0][0], 3)
        self.opening_stock_kg = flt(frappe.db.sql(
            """SELECT COALESCE(SUM(q),0) FROM (
                   SELECT (SELECT qty_after_transaction FROM `tabStock Ledger Entry` s2
                           WHERE s2.warehouse=s.warehouse AND s2.item_code=s.item_code
                           AND s2.posting_datetime < %s AND s2.is_cancelled=0
                           ORDER BY s2.posting_datetime DESC, s2.creation DESC LIMIT 1) q
                   FROM (SELECT DISTINCT warehouse, item_code FROM `tabStock Ledger Entry`
                         WHERE warehouse=%s) s
               ) t""", (start, self.warehouse))[0][0], 3)

    # ------------------------------------------------------------ workflow
    def on_submit(self):
        self.db_set("approval_status", "Submitted")
        self.db_set("closed_by", frappe.session.user)
        log_action("Daily Branch Closing", self.name, "Submit", branch=self.branch,
                   new_value={"sales": self.sales_total, "variance": self.total_variance})

    def on_update_after_submit(self):
        before = self.get_doc_before_save()
        if before and before.approval_status != "Approved" and self.approval_status == "Approved":
            self.db_set("approved_by", frappe.session.user)
            self.db_set("approval_date", now_datetime())
            self._post_variance()

    def _post_variance(self):
        if abs(flt(self.total_variance)) < 0.01 or self.journal_entry:
            return
        settings = get_settings()
        cash_row = next((r for r in self.payments if r.mode_of_payment == "Cash"), None)
        if not cash_row:
            return
        from manase_butcher.accounting_utils import get_payment_account
        cash_account = get_payment_account("Cash", settings.company)
        if not cash_account or not settings.cash_over_short_account:
            frappe.msgprint(_("Cash Over/Short account not configured; variance not posted"))
            return
        variance = flt(self.total_variance)
        accounts = []
        if variance < 0:  # cash short: expense
            accounts.append({"account": settings.cash_over_short_account,
                             "debit": abs(variance), "cost_center": get_branch_cost_center(self.branch)})
            accounts.append({"account": cash_account, "credit": abs(variance)})
        else:  # cash over: income to cash
            accounts.append({"account": cash_account, "debit": variance})
            accounts.append({"account": settings.cash_over_short_account, "credit": variance})
        je = make_journal_entry(settings.company, accounts,
                                posting_date=getdate(self.posting_date),
                                user_remark=f"Cash over/short {self.name}",
                                branch=self.branch)
        self.db_set("journal_entry", je.name)
        log_action("Daily Branch Closing", self.name, "Approval",
                   field_label="cash_variance", old_value=0, new_value=variance,
                   branch=self.branch, reason=self.explanation)

    def on_cancel(self):
        if self.journal_entry:
            je = frappe.get_doc("Journal Entry", self.journal_entry)
            if je.docstatus == 1:
                je.flags.ignore_permissions = True
                je.cancel()
        log_action("Daily Branch Closing", self.name, "Cancel", branch=self.branch)
