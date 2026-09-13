# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
import frappe
from frappe.model.document import Document


class ManaseButcherSettings(Document):
    def validate(self):
        if not self.company and frappe.db.exists("Company", "MANASE BUTCHER LTD"):
            self.company = "MANASE BUTCHER LTD"
        if self.sms_gateway and self.sms_gateway != "Log (development)" and not self.sms_api_url \
                and self.sms_gateway == "Generic HTTP":
            frappe.msgprint("Configure the SMS Gateway URL for non-log delivery.")
