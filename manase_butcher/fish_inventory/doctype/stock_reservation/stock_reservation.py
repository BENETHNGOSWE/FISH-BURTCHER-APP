# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class StockReservation(Document):
    def validate(self):
        if flt(self.reserved_kg) <= 0:
            frappe.throw(_("Reserved KG must be greater than zero"))

    def on_submit(self):
        self.status = self.status or "Reserved"

    def on_cancel(self):
        self.db_set("status", "Released")
        from manase_butcher.doctype_compat import _adjust_bin_reserved
        _adjust_bin_reserved(self.item, self.warehouse, -flt(self.reserved_kg))
