# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
"""Shared fixtures: company, branches, fish items, supplier, customer."""
import frappe
from frappe.utils import flt


COMPANY = "Test Fish Co - MB"


def ensure_company():
    if not frappe.db.exists("Company", COMPANY):
        doc = frappe.get_doc({
            "doctype": "Company",
            "company_name": COMPANY,
            "country": "Tanzania",
            "default_currency": "TZS",
        })
        doc.flags.ignore_permissions = True
        doc.insert()
    # run installer for structure
    from manase_butcher.setup.install import _ensure_company_structure, _ensure_default_branches
    _ensure_company_structure(COMPANY)
    _ensure_default_branches(COMPANY)
    s = frappe.get_single("Manase Butcher Settings")
    s.company = COMPANY
    abbr = frappe.db.get_value("Company", COMPANY, "abbr")
    for kind, field in (("Central Raw", "central_raw_warehouse"),
                        ("Central Processed", "central_processed_warehouse"),
                        ("Waste", "waste_warehouse"),
                        ("Transit", "transit_warehouse"),
                        ("Processing", "processing_warehouse")):
        wh = frappe.db.get_value("Warehouse",
                                 {"company": COMPANY, "custom_mb_warehouse_kind": kind}, "name")
        setattr(s, field, wh)
    s.save(ignore_permissions=True)
    return COMPANY


def ensure_species_and_items():
    if not frappe.db.exists("Fish Species", "Red Snapper"):
        frappe.get_doc({"doctype": "Fish Species",
                        "species_name": "Red Snapper"}).insert(ignore_permissions=True)

    def item(name, group, preparation, rate=0):
        if frappe.db.exists("Item", name):
            return name
        d = frappe.get_doc({
            "doctype": "Item",
            "item_code": name,
            "item_name": name,
            "item_group": group,
            "stock_uom": "Kg",
            "is_stock_item": 1,
            "is_sales_item": 1,
            "standard_selling_rate": rate,
            "custom_mb_is_fish": 1,
            "custom_mb_species": "Red Snapper",
            "custom_mb_freshness": "Fresh",
            "custom_mb_preparation": preparation,
            "custom_mb_sellable": preparation != "Whole",
        })
        d.flags.ignore_permissions = True
        d.insert()
        return d.name

    whole = item("Test Red Snapper - Whole", "Fresh Fish", "Whole")
    cleaned = item("Test Red Snapper - Cleaned", "Processed Fish", "Cleaned", 12000)
    waste = item("Test Fish Waste", "Fish Waste", "Other", 0)
    return whole, cleaned, waste


def ensure_supplier(name="Test Fisherman"):
    if frappe.db.exists("Supplier", name):
        return name
    d = frappe.get_doc({"doctype": "Supplier", "supplier_name": name,
                        "supplier_group": "All Supplier Groups",
                        "custom_mb_supplier_kind": "Fisherman"})
    d.flags.ignore_permissions = True
    d.insert()
    return d.name


def ensure_customer(name="Test Mobile Customer"):
    if frappe.db.exists("Customer", name):
        return name
    d = frappe.get_doc({"doctype": "Customer", "customer_name": name,
                        "customer_group": "All Customer Groups",
                        "territory": "All Territories"})
    d.flags.ignore_permissions = True
    d.insert()
    return d.name
