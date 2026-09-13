# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime

from manase_butcher.audit import log_action
from manase_butcher.branch_utils import get_settings, get_branch_warehouse, get_branch_cost_center
from manase_butcher.stock_utils import make_stock_entry, get_valuation_rate


class FishWasteRecord(Document):
    def validate(self):
        self._set_defaults()
        self._calculate()
        self._check_reasons()

    def _set_defaults(self):
        settings = get_settings()
        if self.branch and not self.warehouse:
            self.warehouse = get_branch_warehouse(self.branch)
        if not self.warehouse:
            self.warehouse = settings.waste_warehouse
        for r in self.items:
            if not r.valuation_rate:
                r.valuation_rate = get_valuation_rate(r.item, self.warehouse)
            r.amount = flt(r.qty_kg) * flt(r.valuation_rate)

    def _calculate(self):
        if not self.items:
            frappe.throw(_("At least one waste line is required"))
        self.total_kg = round(sum(flt(r.qty_kg) for r in self.items), 3)
        self.total_value = round(sum(flt(r.amount) for r in self.items), 2)
        settings = get_settings()
        threshold = flt(settings.waste_approval_kg) or 10
        self.requires_approval = 1 if (
            self.total_kg >= threshold or self.waste_category in ("Unknown Loss",)
        ) else 0

    def _check_reasons(self):
        for r in self.items:
            if flt(r.qty_kg) <= 0:
                frappe.throw(_("Waste KG must be greater than zero"))
            if not (r.reason or "").strip():
                frappe.throw(_("A reason is mandatory for every waste line ({0})").format(r.item))

    def on_submit(self):
        if self.approval_status != "Approved":
            self.db_set("approval_status",
                        "Pending Approval" if self.requires_approval else "Approved")
        if self.approval_status == "Approved":
            self._post_issue()

    def on_update_after_submit(self):
        before = self.get_doc_before_save()
        if before and before.approval_status != "Approved" and self.approval_status == "Approved":
            self.db_set("approved_by", frappe.session.user)
            self.db_set("approval_date", now_datetime())
            self._post_issue()

    def _post_issue(self):
        if self.stock_entry:
            return
        settings = get_settings()
        cost_center = get_branch_cost_center(self.branch) if self.branch else None
        items = [{
            "item": r.item, "qty": flt(r.qty_kg), "uom": "Kg",
            "s_warehouse": self.warehouse,
            "rate": r.valuation_rate or get_valuation_rate(r.item, self.warehouse),
            "expense_account": settings.waste_expense_account,
            "cost_center": cost_center,
        } for r in self.items]
        se = make_stock_entry(
            "Material Issue", items, company=settings.company,
            posting_date=getdate(self.posting_date),
            branch=self.branch, from_doctype="Fish Waste Record", from_docname=self.name,
            stage="Waste", stock_entry_type="Material Issue")
        self.db_set("stock_entry", se.name)
        log_action("Fish Waste Record", self.name, "Approval",
                   field_label="waste", new_value={"kg": self.total_kg,
                                                    "value": self.total_value,
                                                    "category": self.waste_category},
                   branch=self.branch, reason=self.notes)

    def on_cancel(self):
        if self.stock_entry:
            se = frappe.get_doc("Stock Entry", self.stock_entry)
            if se.docstatus == 1:
                se.flags.ignore_permissions = True
                se.cancel()
        log_action("Fish Waste Record", self.name, "Cancel", branch=self.branch)
