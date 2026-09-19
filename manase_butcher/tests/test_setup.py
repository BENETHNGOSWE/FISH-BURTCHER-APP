# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Foundation tests: roles, UOMs, branches provisioning warehouse + cost center."""
import frappe
from frappe.tests.utils import FrappeTestCase

from manase_butcher.tests.utils import ensure_company


class TestSetup(FrappeTestCase):
    def test_roles_exist(self):
        for role in ("Business Owner", "General Manager", "Accountant",
                     "Inventory Manager", "Procurement Officer", "Branch Manager",
                     "Sales Staff", "Cashier", "Processing Staff", "Warehouse Staff",
                     "Delivery Staff", "Customer"):
            self.assertTrue(frappe.db.exists("Role", role), role)

    def test_uom_and_warehouses(self):
        company = ensure_company()
        self.assertTrue(frappe.db.exists("UOM", "Kg"))
        for kind in ("Central Raw", "Central Processed", "Waste", "Transit"):
            self.assertTrue(
                frappe.db.get_value("Warehouse",
                                   {"company": company,
                                    "mb_warehouse_kind": kind}, "name"),
                kind)

    def test_branch_provisions_warehouse_and_cost_center(self):
        company = ensure_company()
        name = frappe.db.get_value("Branch", {"branch_name": "Masaki"})
        self.assertTrue(name)
        branch = frappe.get_doc("Branch", name)
        self.assertTrue(branch.warehouse)
        self.assertTrue(branch.cost_center)
        self.assertEqual(
            frappe.db.get_value("Warehouse", branch.warehouse, "mb_branch"), name)
