# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime

from manase_butcher.audit import log_action
from manase_butcher.branch_utils import get_settings
from manase_butcher.stock_utils import make_stock_entry, get_valuation_rate


class FishProcessing(Document):
    # ------------------------------------------------------------ validation
    def validate(self):
        self._set_defaults()
        self._calculate()
        self._check_conservation()

    def _set_defaults(self):
        settings = get_settings()
        self.company = self.company or settings.company
        self.source_warehouse = self.source_warehouse or settings.central_raw_warehouse
        self.target_warehouse = self.target_warehouse or settings.central_processed_warehouse
        self.waste_warehouse = self.waste_warehouse or settings.waste_warehouse
        self.processing_warehouse = self.processing_warehouse or settings.processing_warehouse

    def _calculate(self):
        self.input_kg = round(sum(flt(r.qty_kg) for r in self.inputs), 3)
        self.output_kg = round(sum(flt(r.qty_kg) for r in self.outputs), 3)
        self.sellable_output_kg = round(sum(flt(r.qty_kg) for r in self.outputs
                                            if not r.is_waste), 3)
        self.waste_kg = round(sum(flt(r.qty_kg) for r in self.outputs if r.is_waste), 3)
        self.yield_pct = round(100 * self.sellable_output_kg / self.input_kg, 2) if self.input_kg else 0
        self.waste_pct = round(100 * self.waste_kg / self.input_kg, 2) if self.input_kg else 0
        for r in self.inputs:
            if not r.valuation_rate:
                r.valuation_rate = get_valuation_rate(r.item, self.source_warehouse)
            r.amount = flt(r.qty_kg) * flt(r.valuation_rate)

    def _check_conservation(self):
        if not self.inputs:
            frappe.throw(_("Input fish is required"))
        if not self.outputs:
            frappe.throw(_("At least one output line is required"))
        if self.input_kg <= 0:
            frappe.throw(_("Input KG must be greater than zero"))
        # Rule 5: input KG = sellable output KG + waste KG
        if abs(self.input_kg - self.output_kg) > max(0.01, self.input_kg * 0.001):
            frappe.throw(
                _("KG does not balance: input {0} KG but outputs total {1} KG "
                  "(sellable {2} + waste {3}). Every input KG must become output or waste.").format(
                    self.input_kg, self.output_kg, self.sellable_output_kg, self.waste_kg))

    # ------------------------------------------------------------ workflow / posting
    def on_submit(self):
        # First workflow submit moves to Pending Approval; nothing is posted yet.
        if self.approval_status not in ("Approved",):
            self.db_set("approval_status", "Pending Approval")
        else:
            self._post_manufacture()

    def on_update_after_submit(self):
        before = self.get_doc_before_save()
        if before and before.approval_status != "Approved" and self.approval_status == "Approved":
            self.db_set("approved_by", frappe.session.user)
            self.db_set("approval_date", now_datetime())
            self._post_manufacture()

    def _post_manufacture(self):
        if self.stock_entry:
            return
        settings = get_settings()
        items = []
        for r in self.inputs:
            items.append({
                "item": r.item, "qty": flt(r.qty_kg), "uom": "Kg",
                "s_warehouse": self.source_warehouse,
                "rate": r.valuation_rate or get_valuation_rate(r.item, self.source_warehouse),
                "batch_no": r.batch,
            })
        finished_good_set = False
        finished_qty = 0
        for r in self.outputs:
            target = self.waste_warehouse if r.is_waste else (
                r.target_warehouse or self.target_warehouse)
            is_finished = bool(not r.is_waste and not finished_good_set)
            if is_finished:
                finished_good_set = True
                finished_qty = flt(r.qty_kg)
            items.append({
                "item": r.item, "qty": flt(r.qty_kg), "uom": "Kg",
                "t_warehouse": target,
                "rate": flt(r.valuation_rate) or 0,
                "is_finished_item": 1 if is_finished else 0,
                # ERPNext v16 uses the legacy scrap flag in Manufacture
                # validation for by-product rows.
                "is_legacy_scrap_item": 1 if r.is_waste else 0,
                "allow_zero_valuation_rate": 1 if (r.is_waste or not r.valuation_rate) else 0,
            })
        additional = []
        if flt(self.processing_cost) > 0:
            account = (frappe.db.get_value("Account",
                        {"account_name": ["like", "%Expenses Included In Valuation%"]}, "name")
                       or settings.stock_adjustment_account)
            if account:
                additional.append({"expense_account": account,
                                   "description": f"Processing cost {self.name}",
                                   "amount": flt(self.processing_cost)})
        se = make_stock_entry(
            "Manufacture", items, company=self.company,
            posting_date=getdate(self.posting_date),
            additional_costs=additional,
            from_doctype="Fish Processing", from_docname=self.name,
            stage="Processing Output", stock_entry_type="Manufacture",
            set_basic_rate=False)
        self.db_set("stock_entry", se.name)
        self._update_batch(se.name)
        log_action("Fish Processing", self.name, "Approval",
                   field_label="approval_status", old_value="Pending Approval",
                   new_value="Approved",
                   branch=None,
                   reason=f"Input {self.input_kg} KG -> {self.sellable_output_kg} sellable + "
                          f"{self.waste_kg} waste; yield {self.yield_pct}%")

    def _update_batch(self, stock_entry):
        if not self.fish_batch:
            return
        try:
            b = frappe.get_doc("Fish Batch", self.fish_batch)
            if b.docstatus == 1:
                b.cancel()
            b.sellable_kg = flt(b.sellable_kg) + self.sellable_output_kg
            b.waste_kg = flt(b.waste_kg) + self.waste_kg
            b.yield_pct = (round(100 * b.sellable_kg / b.received_kg, 2)
                           if flt(b.received_kg) else b.yield_pct)
            b.status = "In Stock"
            b.flags.ignore_permissions = True
            b.save()
            b.submit()
        except Exception:
            frappe.log_error(title="Fish batch update failed", message=frappe.get_traceback())

    def on_cancel(self):
        if self.stock_entry:
            se = frappe.get_doc("Stock Entry", self.stock_entry)
            if se.docstatus == 1:
                se.flags.ignore_permissions = True
                se.cancel()
        log_action("Fish Processing", self.name, "Cancel")
