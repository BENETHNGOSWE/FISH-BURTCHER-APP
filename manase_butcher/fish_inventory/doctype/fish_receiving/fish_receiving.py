# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowtime

from manase_butcher.audit import log_action
from manase_butcher.branch_utils import get_settings


class FishReceiving(Document):
    # ------------------------------------------------------------ validation
    def validate(self):
        self._set_defaults()
        self._calculate_totals()
        self._validate_lines()

    def _set_defaults(self):
        settings = get_settings()
        if not self.company:
            self.company = settings.company
        if not self.warehouse:
            self.warehouse = settings.central_raw_warehouse
        if not self.currency:
            self.currency = settings.default_currency or "TZS"
        for row in self.items:
            row.uom = row.uom or "Kg"
            if row.gross_weight_kg and not row.qty_kg:
                row.qty_kg = flt(row.gross_weight_kg) - flt(row.tare_weight_kg)
            row.amount = flt(row.qty_kg) * flt(row.rate)
            if row.item:
                row.item_name = row.item_name or frappe.db.get_value("Item", row.item, "item_name")
                if not row.species:
                    row.species = frappe.db.get_value("Item", row.item, "custom_mb_species")

    def _calculate_totals(self):
        self.total_qty_kg = round(sum(flt(r.qty_kg) for r in self.items), 3)
        self.total_pieces = sum(flt(r.pieces or 0) for r in self.items)
        self.purchase_total = round(sum(flt(r.amount) for r in self.items), 2)
        landed = sum(flt(c.amount) for c in self.landing_costs if c.account)
        self.total_landed_cost = flt(self.purchase_total) + flt(landed)
        self.landed_cost_per_kg = (self.total_landed_cost / self.total_qty_kg
                                   if self.total_qty_kg else 0)
        self.outstanding_amount = max(0, flt(self.total_landed_cost) - flt(self.paid_amount or 0))
        if self.outstanding_amount == 0 and self.total_landed_cost:
            self.payment_status = "Paid"
        elif flt(self.paid_amount or 0) > 0:
            self.payment_status = "Partly Paid"

    def _validate_lines(self):
        if not self.items:
            frappe.throw(_("At least one fish line is required"))
        for row in self.items:
            if flt(row.qty_kg) <= 0:
                frappe.throw(_("Weight (KG) must be greater than zero for {0}").format(row.item))
            if flt(row.rate) < 0:
                frappe.throw(_("Rate cannot be negative for {0}").format(row.item))

    # ------------------------------------------------------------ submit -> PR
    def on_submit(self):
        pr = self._create_purchase_receipt()
        self.db_set("purchase_receipt", pr.name)
        if self.create_purchase_invoice:
            pi = self._create_purchase_invoice(pr.name)
            if pi:
                self.db_set("purchase_invoice", pi)
        self._create_batches(pr.name)
        log_action("Fish Receiving", self.name, "Submit",
                   new_value={"total_kg": self.total_qty_kg,
                              "landed_cost": self.total_landed_cost})

    def _create_purchase_receipt(self):
        pr = frappe.new_doc("Purchase Receipt")
        pr.supplier = self.supplier
        pr.company = self.company
        pr.posting_date = getdate(self.posting_date)
        pr.posting_time = self.posting_time or nowtime()
        pr.currency = self.currency
        pr.conversion_rate = flt(self.conversion_rate) or 1
        pr.set_warehouse = self.warehouse
        pr.custom_mb_fish_receiving = self.name
        pr.custom_mb_total_kg = self.total_qty_kg
        for row in self.items:
            pr.append("items", {
                "item_code": row.item,
                "item_name": row.item_name,
                "qty": flt(row.qty_kg),
                "uom": row.uom or "Kg",
                "stock_uom": row.uom or "Kg",
                "conversion_factor": 1,
                "rate": flt(row.rate),
                "price_list_rate": flt(row.rate),
                "warehouse": self.warehouse,
                "custom_mb_grade": row.grade,
                "custom_mb_freshness": row.freshness or "Fresh",
                "batch_no": row.batch or None,
            })
        for cost in self.landing_costs:
            if not cost.account or flt(cost.amount) <= 0:
                continue
            pr.append("taxes", {
                "charge_type": "Actual",
                "account_head": cost.account,
                "tax_amount": flt(cost.amount),
                "total_amount": flt(cost.amount),
                "base_tax_amount": flt(cost.amount),
                "category": "Valuation",
                "add_deduct_tax": "Add",
                "description": f"Fish landed cost: {cost.cost_type} {cost.note or ''}".strip(),
            })
        pr.flags.ignore_permissions = True
        pr.insert()
        pr.submit()
        return pr

    def _create_purchase_invoice(self, pr_name):
        try:
            from erpnext.buying.doctype.purchase_receipt.purchase_receipt import (
                make_purchase_invoice)
            pi = make_purchase_invoice(pr_name)
            pi.flags.ignore_permissions = True
            pi.insert()
            pi.submit()
            return pi.name
        except Exception:
            frappe.log_error(title="Purchase Invoice create failed",
                             message=frappe.get_traceback())
            return None

    def _create_batches(self, pr_name):
        from erpnext.stock.doctype.batch.batch import Batch  # noqa
        for row in self.items:
            if row.batch:
                continue
            try:
                b = frappe.new_doc("Batch")
                b.item = row.item
                b.batch_id = None
                b.custom_mb_supplier = self.supplier
                b.custom_mb_received_date = getdate(self.posting_date)
                b.flags.ignore_permissions = True
                b.insert()
                row.db_set("batch", b.name)
                fb = frappe.new_doc("Fish Batch")
                fb.supplier = self.supplier
                fb.fish_receiving = self.name
                fb.erpnext_batch = b.name
                fb.item = row.item
                fb.species = row.species
                fb.grade = row.grade
                fb.received_date = getdate(self.posting_date)
                fb.received_kg = flt(row.qty_kg)
                fb.status = "Received"
                fb.flags.ignore_permissions = True
                fb.insert()
                fb.submit()
                b.db_set("custom_mb_fish_batch", fb.name)
            except Exception:
                frappe.log_error(title="Fish batch create failed",
                                 message=frappe.get_traceback())

    # ------------------------------------------------------------ cancel
    def on_cancel(self):
        if self.purchase_invoice:
            self._cancel("Purchase Invoice", self.purchase_invoice)
        if self.purchase_receipt:
            self._cancel("Purchase Receipt", self.purchase_receipt)
        log_action("Fish Receiving", self.name, "Cancel", branch=None)

    def _cancel(self, dt, name):
        try:
            doc = frappe.get_doc(dt, name)
            if doc.docstatus == 1:
                doc.flags.ignore_permissions = True
                doc.cancel()
        except Exception:
            frappe.log_error(title=f"Cancel {dt} {name} failed", message=frappe.get_traceback())
