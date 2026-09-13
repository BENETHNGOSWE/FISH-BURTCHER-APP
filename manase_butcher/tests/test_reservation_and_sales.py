# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Reservation/oversell and POS tests (spec section 29, steps 10-25)."""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate

from manase_butcher.tests.utils import (
    ensure_company, ensure_species_and_items, ensure_customer)
from manase_butcher.branch_utils import get_settings
from manase_butcher.stock_utils import available_kg, make_stock_entry


class TestReservationSales(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = ensure_company()
        cls.whole, cls.cleaned, cls.waste_item = ensure_species_and_items()
        cls.customer = ensure_customer()
        cls.settings = get_settings()
        cls.branch = frappe.db.get_value("Branch", {"branch_name": "Sinza"}, "name")
        cls.wh = frappe.db.get_value("Branch", cls.branch, "warehouse")
        cls._seed_20kg()

    @classmethod
    def _seed_20kg(cls):
        # put 20 KG directly into the branch warehouse via material receipt
        rate = frappe.db.get_value("Item", cls.cleaned, "valuation_rate") or 8000
        make_stock_entry("Material Receipt",
                         [{"item": cls.cleaned, "qty": 20, "t_warehouse": cls.wh,
                           "rate": rate, "allow_zero_valuation_rate": 1}],
                         company=cls.company, branch=cls.branch,
                         stock_entry_type="Material Receipt")

    def test_available_kg(self):
        self.assertEqual(available_kg(self.cleaned, self.wh), 20)

    def test_oversell_rejected(self):
        def order(kg):
            doc = frappe.get_doc({
                "doctype": "Customer Order",
                "customer": self.customer,
                "customer_name": "Test Mobile Customer",
                "phone": "+255700000000",
                "branch": self.branch,
                "warehouse": self.wh,
                "order_type": "Pickup",
                "items": [{"item": self.cleaned, "qty_kg": kg, "rate": 12000}],
            })
            doc.price_and_check_availability()
            doc.flags.ignore_permissions = True
            doc.insert()
            doc.reserve_stock()
            return doc

        oa = order(10)
        self.assertEqual(available_kg(self.cleaned, self.wh), 10)
        ob = order(8)
        self.assertEqual(available_kg(self.cleaned, self.wh), 2)
        with self.assertRaises(frappe.ValidationError):
            order(5)  # only 2 KG left -> must be rejected (Rule 4)

        # cancellation releases reserved KG
        frappe.local.flags.in_mobile_api = True
        ob.transition("Cancelled", reason="test")
        frappe.local.flags.in_mobile_api = False
        self.assertGreaterEqual(available_kg(self.cleaned, self.wh), 10)
