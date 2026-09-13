# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""End-to-end KG conservation test (spec section 42, steps 1-9 and 24)."""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate

from manase_butcher.tests.utils import (
    ensure_company, ensure_species_and_items, ensure_supplier)
from manase_butcher.branch_utils import get_settings
from manase_butcher.stock_utils import available_kg


class TestKGTracking(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = ensure_company()
        cls.whole, cls.cleaned, cls.waste_item = ensure_species_and_items()
        cls.supplier = ensure_supplier()
        cls.settings = get_settings()

    def _stock(self, item, wh):
        return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": wh},
                                       "actual_qty") or 0)

    def test_full_flow_conserves_kg(self):
        # 1-4. Receive 500 KG Red Snapper into Central Raw
        recv = frappe.get_doc({
            "doctype": "Fish Receiving",
            "supplier": self.supplier,
            "posting_date": getdate(),
            "warehouse": self.settings.central_raw_warehouse,
            "items": [{
                "item": self.whole, "qty_kg": 500, "rate": 8000,
                "freshness": "Fresh", "grade": "A",
            }],
            "landing_costs": [
                {"cost_type": "Transport", "amount": 100000},
                {"cost_type": "Handling", "amount": 50000},
            ],
        })
        recv.flags.ignore_permissions = True
        recv.insert()
        recv.submit()
        self.assertEqual(self._stock(self.whole, self.settings.central_raw_warehouse), 500)
        self.assertAlmostEqual(flt(recv.total_landed_cost), 4_150_000, places=2)

        # 5-7. Process: 470 cleaned + 30 waste
        proc = frappe.get_doc({
            "doctype": "Fish Processing",
            "posting_date": getdate(),
            "source_warehouse": self.settings.central_raw_warehouse,
            "target_warehouse": self.settings.central_processed_warehouse,
            "waste_warehouse": self.settings.waste_warehouse,
            "approval_status": "Approved",
            "inputs": [{"item": self.whole, "qty_kg": 500}],
            "outputs": [
                {"item": self.cleaned, "qty_kg": 470},
                {"item": self.waste_item, "qty_kg": 30, "is_waste": 1,
                 "target_warehouse": self.settings.waste_warehouse},
            ],
        })
        proc.flags.ignore_permissions = True
        proc.insert()
        proc.submit()
        self.assertAlmostEqual(flt(proc.yield_pct), 94.0, places=1)
        self.assertAlmostEqual(flt(proc.waste_pct), 6.0, places=1)
        self.assertEqual(self._stock(self.cleaned, self.settings.central_processed_warehouse), 470)
        self.assertEqual(self._stock(self.whole, self.settings.central_raw_warehouse), 0)
        self.assertEqual(self._stock(self.waste_item, self.settings.waste_warehouse), 30)

        # 8. Transfer 100 KG to Masaki; receive 98 KG (variance -2, reason mandatory)
        branch = frappe.db.get_value("Branch", {"branch_name": "Masaki"}, "name")
        branch_wh = frappe.db.get_value("Branch", branch, "warehouse")
        tr = frappe.get_doc({
            "doctype": "Fish Stock Transfer",
            "posting_date": getdate(),
            "source_warehouse": self.settings.central_processed_warehouse,
            "transit_warehouse": self.settings.transit_warehouse,
            "target_branch": branch,
            "target_warehouse": branch_wh,
            "items": [{"item": self.cleaned, "sent_kg": 100, "received_kg": 98,
                       "variance_reason": "ice melt / leakage"}],
        })
        tr.flags.ignore_permissions = True
        tr.insert()
        tr.submit()
        tr.approve()
        tr.dispatch()
        tr.receive(create_waste_for_variance=1)
        self.assertEqual(self._stock(self.cleaned, branch_wh), 98)

        # KG Movement report reconciles with ledger (difference must be 0)
        from manase_butcher.report.kg_movement.kg_movement import execute
        cols, rows = execute({"from_date": getdate(), "to_date": getdate(),
                              "warehouse": self.settings.central_processed_warehouse})
        row = next((r for r in rows if r["item"] == self.cleaned), None)
        self.assertIsNotNone(row)
        self.assertEqual(flt(row["difference"], 3), 0)

        # availability at branch = 98 KG
        self.assertEqual(available_kg(self.cleaned, branch_wh), 98)
