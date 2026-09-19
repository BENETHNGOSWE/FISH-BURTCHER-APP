# -*- coding: utf-8 -*-
"""Idempotent custom-field provisioning (runs on every bench migrate)."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
    "Item": [
        {"fieldname": "mb_manase_section", "label": "MANASE BUTCHER Fish Data",
         "fieldtype": "Section Break", "insert_after": "stock_uom"},
        {"fieldname": "mb_is_fish", "label": "Is Fish Item", "fieldtype": "Check",
         "insert_after": "mb_manase_section", "default": "0"},
        {"fieldname": "mb_species", "label": "Fish Species", "fieldtype": "Link",
         "options": "Fish Species", "insert_after": "mb_is_fish"},
        {"fieldname": "mb_fish_category", "label": "Fish Category", "fieldtype": "Select",
         "options": "\nWhite Fish\nOily Fish\nShellfish\nProcessed Cut\nWaste\nOther",
         "insert_after": "mb_species"},
        {"fieldname": "mb_grade", "label": "Grade", "fieldtype": "Select",
         "options": "\nA\nB\nC", "insert_after": "mb_fish_category"},
        {"fieldname": "mb_size", "label": "Size", "fieldtype": "Select",
         "options": "\nSmall\nMedium\nLarge\nExtra Large", "insert_after": "mb_grade"},
        {"fieldname": "mb_freshness", "label": "Fresh / Frozen", "fieldtype": "Select",
         "options": "Fresh\nFrozen", "insert_after": "mb_size", "default": "Fresh"},
        {"fieldname": "mb_preparation", "label": "Preparation", "fieldtype": "Select",
         "options": "\nWhole\nCleaned\nFillet\nSteak\nCut\nOther", "insert_after": "mb_freshness"},
        {"fieldname": "mb_sellable", "label": "Sellable (mobile catalog)", "fieldtype": "Check",
         "insert_after": "mb_preparation", "default": "0"},
    ],
    "Warehouse": [
        {"fieldname": "mb_branch", "label": "MANASE Branch", "fieldtype": "Link",
         "options": "Branch", "insert_after": "warehouse_type", "read_only": 0},
        {"fieldname": "mb_warehouse_kind", "label": "Warehouse Kind", "fieldtype": "Select",
         "options": "\nCentral Raw\nCentral Processed\nProcessing\nWaste\nTransit\nBranch",
         "insert_after": "mb_branch"},
    ],
    "Bin": [
        {"fieldname": "mb_custom_reserved_kg", "label": "Custom Reserved KG",
         "fieldtype": "Float", "precision": "3", "default": "0", "read_only": 1},
    ],
    "Batch": [
        {"fieldname": "mb_supplier", "label": "Supplier", "fieldtype": "Link",
         "options": "Supplier"},
        {"fieldname": "mb_fish_batch", "label": "Fish Batch", "fieldtype": "Link",
         "options": "Fish Batch"},
        {"fieldname": "mb_received_date", "label": "Received Date", "fieldtype": "Date"},
    ],
    "Purchase Receipt": [
        {"fieldname": "mb_fish_receiving", "label": "Fish Receiving", "fieldtype": "Link",
         "options": "Fish Receiving", "read_only": 1},
        {"fieldname": "mb_total_kg", "label": "Total KG", "fieldtype": "Float",
         "precision": "3", "read_only": 1},
    ],
    "Purchase Receipt Item": [
        {"fieldname": "mb_grade", "label": "Grade", "fieldtype": "Select",
         "options": "\nA\nB\nC"},
        {"fieldname": "mb_freshness", "label": "Fresh/Frozen", "fieldtype": "Select",
         "options": "Fresh\nFrozen"},
    ],
    "Stock Entry": [
        {"fieldname": "mb_branch", "label": "MANASE Branch", "fieldtype": "Link",
         "options": "Branch"},
        {"fieldname": "mb_stage", "label": "KG Movement Stage", "fieldtype": "Select",
         "options": "\nReceiving\nProcessing Input\nProcessing Output\nWaste\n"
                    "Transfer Dispatch\nTransfer Receipt\nSale\nReturn\nAdjustment"},
        {"fieldname": "mb_fish_processing", "label": "Fish Processing", "fieldtype": "Link",
         "options": "Fish Processing", "read_only": 1},
        {"fieldname": "mb_fish_waste_record", "label": "Fish Waste Record", "fieldtype": "Link",
         "options": "Fish Waste Record", "read_only": 1},
        {"fieldname": "mb_fish_transfer", "label": "Fish Stock Transfer", "fieldtype": "Link",
         "options": "Fish Stock Transfer", "read_only": 1},
    ],
    "Stock Reservation Entry": [
        {"fieldname": "mb_customer_order", "label": "Customer Order", "fieldtype": "Link",
         "options": "Customer Order", "read_only": 1},
    ],
    "Sales Invoice": [
        {"fieldname": "mb_branch", "label": "MANASE Branch", "fieldtype": "Link",
         "options": "Branch", "reqd": 0},
        {"fieldname": "mb_sales_channel", "label": "Sales Channel", "fieldtype": "Select",
         "options": "Walk-in\nWholesale\nRestaurant\nMobile", "default": "Walk-in"},
        {"fieldname": "mb_customer_order", "label": "Customer Order", "fieldtype": "Link",
         "options": "Customer Order", "read_only": 1},
        {"fieldname": "mb_total_kg", "label": "Total KG", "fieldtype": "Float",
         "precision": "3", "read_only": 1},
        {"fieldname": "mb_sales_staff", "label": "Sales Staff", "fieldtype": "Link",
         "options": "Employee"},
    ],
    "Sales Invoice Item": [
        {"fieldname": "mb_weight_kg", "label": "Weight (KG)", "fieldtype": "Float",
         "precision": "3"},
    ],
    "Payment Entry": [
        {"fieldname": "mb_branch", "label": "MANASE Branch", "fieldtype": "Link",
         "options": "Branch"},
        {"fieldname": "mb_mobile_provider", "label": "Mobile Money Provider",
         "fieldtype": "Select",
         "options": "\nM-Pesa\nTigo Pesa\nAirtel Money\nHaloPesa"},
        {"fieldname": "mb_mobile_reference", "label": "Mobile Txn Reference",
         "fieldtype": "Data"},
    ],
    "Journal Entry": [
        {"fieldname": "mb_branch", "label": "MANASE Branch", "fieldtype": "Link",
         "options": "Branch"},
    ],
    "Item Price"
    : [
        {"fieldname": "mb_branch", "label": "Branch (blank = all)", "fieldtype": "Link",
         "options": "Branch"},
        {"fieldname": "mb_price_type", "label": "MANASE Price Type", "fieldtype": "Select",
         "options": "Retail\nWholesale\nRestaurant\nHotel\nSpecial\nBranch",
         "default": "Retail"},
    ],
    "Customer": [
        {"fieldname": "mb_preferred_branch", "label": "Preferred Branch", "fieldtype": "Link",
         "options": "Branch"},
        {"fieldname": "mb_phone_verified", "label": "Phone Verified", "fieldtype": "Check",
         "default": "0"},
    ],
    "Supplier": [
        {"fieldname": "mb_supplier_kind", "label": "Supplier Kind", "fieldtype": "Select",
         "options": "Fisherman\nCooperative\nWholesaler\nImporter\nOther",
         "default": "Fisherman"},
    ],
    "User": [
        {"fieldname": "mb_dashboard_branch", "label": "Default Dashboard Branch",
         "fieldtype": "Link", "options": "Branch"},
    ],
}


def setup_custom_fields():
    create_custom_fields(CUSTOM_FIELDS)
    frappe.db.commit()
