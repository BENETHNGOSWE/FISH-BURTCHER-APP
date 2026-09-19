# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Expected stock is *derived* from the ledger; the physical count is entered;
approval posts a standard Stock Reconciliation for the reasoned variance.
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, get_datetime, now_datetime, add_days

from manase_butcher.audit import log_action
from manase_butcher.branch_utils import (
    get_settings, get_branch_warehouse, get_branch_cost_center,
    ROLE_OWNER, ROLE_GM, ROLE_INVENTORY, ROLE_BRANCH_MANAGER)
from manase_butcher.stock_utils import movement_kg, get_valuation_rate


class BranchStockReconciliation(Document):
    def validate(self):
        if self.branch and not self.warehouse:
            self.warehouse = get_branch_warehouse(self.branch)
        self._calculate()
        self._validate_reasons()

    def _calculate(self):
        self.total_expected_kg = round(sum(flt(r.expected_kg) for r in self.items), 3)
        self.total_physical_kg = round(sum(flt(r.physical_kg) for r in self.items), 3)
        self.total_variance_kg = round(self.total_physical_kg - self.total_expected_kg, 3)
        self.total_variance_value = round(sum(flt(r.variance_value) for r in self.items), 2)
        for r in self.items:
            r.variance_kg = round(flt(r.physical_kg) - flt(r.expected_kg), 3)
            if not r.valuation_rate:
                r.valuation_rate = get_valuation_rate(r.item, self.warehouse)
            r.variance_value = flt(r.variance_kg) * flt(r.valuation_rate)

    def _validate_reasons(self):
        settings = get_settings()
        threshold = flt(settings.variance_approval_kg)
        for r in self.items:
            if self.approval_status in ("Submitted", "Reviewed", "Approved"):
                if threshold and abs(flt(r.variance_kg)) >= threshold and not (r.reason or "").strip():
                    frappe.throw(_("Reason mandatory for {0}: variance {1} KG").format(
                        r.item_name or r.item, r.variance_kg))

    # ------------------------------------------------------------ fetch ledger
    @frappe.whitelist()
    def fetch_expected(self):
        if self.docstatus == 1:
            frappe.throw(_("Cannot refetch a submitted reconciliation"))
        start, end = self._period()
        items = self._relevant_items(start, end)
        rows = []
        for item in items:
            opening = self._opening(item, start)
            mv = movement_kg(item, [self.warehouse], start, end)
            received = mv["purchases"] + mv["transfers_in"] + mv["material_receipt_other"]
            expected = (opening + received
                        + mv["transfers_in"] * 0  # counted once in received
                        + mv["sales_returns"] + mv["adjustments"] + mv["processing_out"]
                        - abs(mv["transfers_out"]) - abs(mv["sales"]) - abs(mv["waste"])
                        + mv["processing_in"])
            # processing at branch is atypical; purchases+transfers are the inbound side
            existing_physical = {r.item: r.physical_kg for r in self.items}
            rows.append({
                "item": item,
                "item_name": frappe.db.get_value("Item", item, "item_name"),
                "opening_kg": round(opening, 3),
                "received_kg": round(received, 3),
                "transferred_in_kg": round(mv["transfers_in"], 3),
                "transferred_out_kg": round(abs(mv["transfers_out"]), 3),
                "sales_kg": round(abs(mv["sales"]), 3),
                "waste_kg": round(abs(mv["waste"]), 3),
                "returns_kg": round(mv["sales_returns"], 3),
                "adjustments_kg": round(mv["adjustments"], 3),
                "expected_kg": round(
                    opening + received + mv["sales_returns"] + mv["adjustments"]
                    - abs(mv["transfers_out"]) - abs(mv["sales"]) - abs(mv["waste"]), 3),
                "physical_kg": existing_physical.get(item, 0),
                "valuation_rate": get_valuation_rate(item, self.warehouse),
            })
        self.set("items", [])
        for r in rows:
            self.append("items", r)
        self._calculate()
        self.save()
        return len(rows)

    def _period(self):
        end = get_datetime(f"{getdate(self.posting_date)} 23:59:59")
        # since the last approved reconciliation for this warehouse
        last = frappe.db.get_value(
            "Branch Stock Reconciliation",
            {"warehouse": self.warehouse, "approval_status": "Approved", "docstatus": 1,
             "name": ["!=", self.name]},
            "posting_date", order_by="posting_date desc")
        start_date = add_days(getdate(last), 1) if last else getdate(self.posting_date)
        return get_datetime(f"{start_date} 00:00:00"), end

    def _opening(self, item, start):
        row = frappe.db.sql(
            """SELECT COALESCE(qty_after_transaction, 0) FROM `tabStock Ledger Entry`
               WHERE item_code=%s AND warehouse=%s AND posting_datetime < %s AND is_cancelled=0
               ORDER BY posting_datetime DESC, creation DESC LIMIT 1""",
            (item, self.warehouse, start))
        return flt(row[0][0]) if row else 0

    def _relevant_items(self, start, end):
        items = set(frappe.db.sql_list(
            """SELECT DISTINCT item_code FROM `tabStock Ledger Entry`
               WHERE warehouse=%s AND posting_datetime BETWEEN %s AND %s AND is_cancelled=0""",
            (self.warehouse, start, end)))
        bins = frappe.db.sql_list(
            "SELECT item_code FROM tabBin WHERE warehouse=%s AND (actual_qty <> 0 OR reserved_qty <> 0)",
            (self.warehouse,))
        items.update(bins)
        return sorted(items)

    # ------------------------------------------------------------ workflow
    def on_submit(self):
        self.db_set("approval_status", "Submitted")
        log_action("Branch Stock Reconciliation", self.name, "Submit",
                   branch=self.branch,
                   new_value={"expected": self.total_expected_kg,
                              "physical": self.total_physical_kg})

    def on_update_after_submit(self):
        before = self.get_doc_before_save()
        new = self.approval_status
        if not before:
            return
        if before.approval_status != "Approved" and new == "Approved":
            roles = set(frappe.get_roles())
            if not (roles & {ROLE_OWNER, ROLE_GM, ROLE_INVENTORY, "System Manager",
                            "Stock Manager", "Administrator"}):
                frappe.throw(_("Only Inventory Manager / GM can approve reconciliation"),
                             frappe.PermissionError)
            self._post_reconciliation()
            self.db_set("approved_by", frappe.session.user)
            self.db_set("approval_date", now_datetime())

    def _post_reconciliation(self):
        if self.stock_reconciliation:
            return
        settings = get_settings()
        lines = [r for r in self.items
                 if abs(flt(r.variance_kg)) > 0.0005]
        sr = frappe.new_doc("Stock Reconciliation")
        sr.company = settings.company
        sr.purpose = "Stock Reconciliation"
        sr.posting_date = getdate(self.posting_date)
        sr.posting_time = "23:59:00"
        sr.expense_account = settings.stock_adjustment_account
        sr.cost_center = get_branch_cost_center(self.branch)
        for r in lines:
            sr.append("items", {
                "item_code": r.item,
                "warehouse": self.warehouse,
                "qty": flt(r.physical_kg),
                "valuation_rate": flt(r.valuation_rate),
            })
        if not lines:
            log_action("Branch Stock Reconciliation", self.name, "Approval",
                       branch=self.branch, reason="No variance")
            return
        sr.flags.ignore_permissions = True
        sr.insert()
        sr.mb_branch = self.branch
        sr.save(ignore_permissions=True)
        sr.submit()
        self.db_set("stock_reconciliation", sr.name)
        log_action("Branch Stock Reconciliation", self.name, "Approval",
                   field_label="variance",
                   old_value=self.total_expected_kg, new_value=self.total_physical_kg,
                   branch=self.branch, reason=self.notes)

    def on_cancel(self):
        if self.stock_reconciliation:
            sr = frappe.get_doc("Stock Reconciliation", self.stock_reconciliation)
            if sr.docstatus == 1:
                sr.flags.ignore_permissions = True
                sr.cancel()
        log_action("Branch Stock Reconciliation", self.name, "Cancel", branch=self.branch)
