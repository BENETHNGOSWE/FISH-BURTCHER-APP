# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class FishBatch(Document):
    def validate(self):
        if flt(self.received_kg) <= 0:
            frappe.throw(_("Received KG is required"))
        if flt(self.sellable_kg) + flt(self.waste_kg) > flt(self.received_kg) + 0.01:
            frappe.throw(_("Sellable + waste KG cannot exceed received KG"))
        if flt(self.received_kg):
            self.yield_pct = round(100 * flt(self.sellable_kg) / flt(self.received_kg), 2)

    def on_submit(self):
        if self.erpnext_batch and self.item and self.supplier:
            frappe.db.set_value("Batch", self.erpnext_batch, {
                "mb_supplier": self.supplier,
                "mb_fish_batch": self.name,
                "mb_received_date": getdate(self.received_date),
            }, update_modified=False)

    def on_cancel(self):
        # guard: cannot cancel a batch already distributed/sold
        if flt(self.sold_kg) > 0 or self.status in ("Distributed",):
            frappe.throw(_("Batch already distributed; reverse the transfers/sales first"))
