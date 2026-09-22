# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Two-leg fish transfer: source -> in-transit -> branch, recording sent KG,
received KG and variance (reason mandatory). Status machine with role checks.
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime

from manase_butcher.audit import log_action
from manase_butcher.branch_utils import (
    get_settings, get_branch_warehouse, assert_branch_access,
    ROLE_INVENTORY, ROLE_WAREHOUSE, ROLE_OWNER, ROLE_GM, ROLE_BRANCH_MANAGER,
)
from manase_butcher.stock_utils import make_stock_entry

APPROVERS = (ROLE_OWNER, ROLE_GM, ROLE_INVENTORY, "System Manager", "Administrator")
DISPATCHERS = (ROLE_OWNER, ROLE_GM, ROLE_INVENTORY, ROLE_WAREHOUSE,
               "Stock Manager", "System Manager", "Administrator")


class FishStockTransfer(Document):
    def validate(self):
        self._set_defaults()
        self._calculate()
        self._validate_reasons()

    def _set_defaults(self):
        settings = get_settings()
        self.company = settings.company
        self.transit_warehouse = self.transit_warehouse or settings.transit_warehouse
        if self.target_branch and not self.target_warehouse:
            self.target_warehouse = get_branch_warehouse(self.target_branch)
        for r in self.items:
            if r.item and not r.item_name:
                r.item_name = frappe.db.get_value("Item", r.item, "item_name")

    def _calculate(self):
        if not self.items:
            frappe.throw(_("At least one fish line is required"))
        self.total_sent_kg = round(sum(flt(r.sent_kg) for r in self.items), 3)
        self.total_received_kg = round(sum(flt(r.received_kg or 0) for r in self.items), 3)
        self.total_variance_kg = round(sum(
            flt(r.received_kg or 0) - flt(r.sent_kg) for r in self.items), 3)

    def _validate_reasons(self):
        if self.status in ("Received", "Completed"):
            for r in self.items:
                r.received_kg = r.received_kg or 0
                if abs(flt(r.received_kg) - flt(r.sent_kg)) > 0.001 and not r.variance_reason:
                    frappe.throw(_("Variance reason required for {0} (sent {1}, received {2} KG)").format(
                        r.item, r.sent_kg, r.received_kg))
                if flt(r.received_kg) > flt(r.sent_kg) + 0.001:
                    frappe.throw(_("Received KG cannot exceed sent KG for {0}").format(r.item))

    def on_submit(self):
        self.db_set("status", "Submitted")
        log_action("Fish Stock Transfer", self.name, "Submit",
                   branch=self.target_branch, new_value={"sent_kg": self.total_sent_kg})

    # ------------------------------------------------------------ actions
    @frappe.whitelist()
    def approve(self):
        self._require_any(APPROVERS)
        if self.status not in ("Submitted", "Draft"):
            frappe.throw(_("Only submitted transfers can be approved"))
        self.db_set("status", "Approved")
        self.status = "Approved"
        log_action("Fish Stock Transfer", self.name, "Approval", branch=self.target_branch)

    @frappe.whitelist()
    def dispatch(self):
        self._require_any(DISPATCHERS)
        if self.status == "Dispatched":
            return self.get("outbound_stock_entry")
        if self.status != "Approved":
            frappe.throw(_("Transfer must be Approved before dispatch"))
        for r in self.items:
            if flt(r.sent_kg) <= 0:
                frappe.throw(_("Sent KG required for {0}").format(r.item))
        items = [{
            "item": r.item, "qty": flt(r.sent_kg), "uom": "Kg",
            "s_warehouse": self.source_warehouse,
            "t_warehouse": self.transit_warehouse,
        } for r in self.items]
        company = self.get("company") or get_settings().company
        se = make_stock_entry("Material Transfer", items, company=company,
                              posting_date=getdate(self.posting_date),
                              from_doctype="Fish Stock Transfer", from_docname=self.name,
                              stage="Transfer Dispatch",
                              stock_entry_type="Material Transfer", set_basic_rate=True)
        self.db_set("outbound_stock_entry", se.name)
        self.db_set("dispatched_by", frappe.session.user)
        self.db_set("dispatched_at", now_datetime())
        self.db_set("status", "Dispatched")
        log_action("Fish Stock Transfer", self.name, "Update",
                   field_label="status", new_value="Dispatched",
                   branch=self.target_branch)

    @frappe.whitelist()
    def receive(self, create_waste_for_variance=1):
        if self.status in ("Completed", "Received"):
            return self.get("inbound_stock_entry")
        roles = set(frappe.get_roles())
        if not (roles & set((ROLE_OWNER, ROLE_GM, ROLE_INVENTORY, ROLE_BRANCH_MANAGER,
                            ROLE_WAREHOUSE, "Stock Manager", "System Manager", "Administrator"))):
            frappe.throw(_("Not authorised to receive transfers"), frappe.PermissionError)
        assert_branch_access(self.target_branch)
        if self.status != "Dispatched":
            frappe.throw(_("Only dispatched transfers can be received"))
        self._calculate()
        self._validate_reasons()
        items = []
        for r in self.items:
            received = flt(r.received_kg or 0)
            if received <= 0:
                continue
            items.append({
                "item": r.item, "qty": received, "uom": "Kg",
                "s_warehouse": self.transit_warehouse,
                "t_warehouse": self.target_warehouse,
            })
        se = None
        if items:
            company = self.get("company") or get_settings().company
            se = make_stock_entry("Material Transfer", items, company=company,
                                  posting_date=getdate(self.posting_date),
                                  branch=self.target_branch,
                                  from_doctype="Fish Stock Transfer", from_docname=self.name,
                                  stage="Transfer Receipt",
                                  stock_entry_type="Material Transfer", set_basic_rate=False)
        self.db_set("inbound_stock_entry", se.name if se else None)
        self.db_set("received_by", frappe.session.user)
        self.db_set("received_at", now_datetime())
        self.db_set("status", "Completed")
        # missing KG in transit -> documented waste (never unexplained)
        if cint_bool(create_waste_for_variance) and self.total_variance_kg < -0.001:
            self._record_transfer_variance()
        log_action("Fish Stock Transfer", self.name, "Update",
                   field_label="received",
                   old_value={"sent": self.total_sent_kg},
                   new_value={"received": self.total_received_kg,
                              "variance": self.total_variance_kg},
                   branch=self.target_branch)

    def _record_transfer_variance(self):
        try:
            wr = frappe.new_doc("Fish Waste Record")
            wr.posting_date = getdate(self.posting_date)
            wr.branch = self.target_branch
            wr.warehouse = self.transit_warehouse
            wr.waste_category = "Transfer Discrepancy"
            wr.approval_status = "Approved"
            wr.notes = f"Short receipt against {self.name}"
            for r in self.items:
                missing = flt(r.sent_kg) - flt(r.received_kg or 0)
                if missing > 0.001:
                    wr.append("items", {
                        "item": r.item,
                        "qty_kg": missing,
                        "reason": f"In-transit discrepancy on {self.name}: {r.variance_reason or 'no note'}",
                    })
            wr.flags.ignore_permissions = True
            wr.insert()
            wr.submit()
        except Exception:
            frappe.log_error(title="Transfer variance waste record failed",
                             message=frappe.get_traceback())

    def on_cancel(self):
        for field in ("outbound_stock_entry", "inbound_stock_entry"):
            name = self.get(field)
            if name:
                se = frappe.get_doc("Stock Entry", name)
                if se.docstatus == 1:
                    se.flags.ignore_permissions = True
                    se.cancel()
        self.db_set("status", "Cancelled")
        log_action("Fish Stock Transfer", self.name, "Cancel", branch=self.target_branch)

    def _require_any(self, role_tuple):
        if not (set(frappe.get_roles()) & set(role_tuple)):
            frappe.throw(_("Not authorised for this transfer action"), frappe.PermissionError)


def cint_bool(v):
    if isinstance(v, bool):
        return v
    return 1 if str(v).lower() in ("1", "true", "yes") else 0
