# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Branch expense. Approval posts a Journal Entry:
Dr Expense (branch cost center) / Cr Cash or wallet/bank (branch).
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime

from manase_butcher.audit import log_action
from manase_butcher.branch_utils import (
    get_settings, get_branch_cost_center, assert_branch_access,
    ROLE_OWNER, ROLE_GM, ROLE_ACCOUNTANT)
from manase_butcher.accounting_utils import make_journal_entry, get_payment_account

CATEGORY_ACCOUNT_HINT = {
    "Rent": "Rent",
    "Transport": "Transport",
    "Fuel": "Fuel",
    "Electricity": "Electricity",
    "Water": "Water",
    "Packaging": "Packaging",
    "Maintenance": "Maintenance",
    "Staff Meals": "Staff Meals",
}


class FishExpense(Document):
    def validate(self):
        settings = get_settings()
        self.company = settings.company
        self.cost_center = self.cost_center or get_branch_cost_center(self.branch)
        if self.branch:
            assert_branch_access(self.branch)
        if flt(self.amount) <= 0:
            frappe.throw(_("Expense amount must be greater than zero"))
        if not self.payment_account and self.mode_of_payment:
            self.payment_account = get_payment_account(self.mode_of_payment, self.company)

    def on_submit(self):
        limit = flt(get_settings().expense_approval_limit or 0)
        if self.approval_status != "Approved":
            self.db_set("approval_status",
                        "Pending Approval" if limit and self.amount > limit else "Approved")
        if self.approval_status == "Approved":
            self._post()

    def on_update_after_submit(self):
        before = self.get_doc_before_save()
        if before and before.approval_status != "Approved" and self.approval_status == "Approved":
            roles = set(frappe.get_roles())
            limit = flt(get_settings().expense_approval_limit or 0)
            can = roles & {ROLE_OWNER, ROLE_GM, ROLE_ACCOUNTANT,
                           "System Manager", "Administrator"} or (
                               self.amount <= limit and "Branch Manager" in roles)
            if not can:
                frappe.throw(_("You cannot approve this expense"), frappe.PermissionError)
            self.db_set("approved_by", frappe.session.user)
            self.db_set("approval_date", now_datetime())
            self._post()

    def _post(self):
        if self.journal_entry:
            return
        if not self.payment_account:
            frappe.throw(_("Select a Mode of Payment with a configured account"))
        accounts = [
            {"account": self.expense_account, "debit": flt(self.amount),
             "cost_center": self.cost_center, "remark": f"{self.expense_category}: {self.description or ''}"},
            {"account": self.payment_account, "credit": flt(self.amount),
             "party_type": "Supplier" if self.supplier else None, "party": self.supplier},
        ]
        je = make_journal_entry(
            self.company, accounts, posting_date=getdate(self.posting_date),
            user_remark=f"Fish expense {self.name} - {self.expense_category}",
            branch=self.branch)
        self.db_set("journal_entry", je.name)
        log_action("Fish Expense", self.name, "Approval",
                   field_label="amount", new_value=self.amount, branch=self.branch,
                   reason=self.description)

    def on_cancel(self):
        if self.journal_entry:
            je = frappe.get_doc("Journal Entry", self.journal_entry)
            if je.docstatus == 1:
                je.flags.ignore_permissions = True
                je.cancel()
        log_action("Fish Expense", self.name, "Cancel", branch=self.branch)
