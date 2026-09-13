# -*- coding: utf-8 -*-
"""MANASE BUTCHER Frappe application hooks."""
from . import __version__ as app_version

app_name = "manase_butcher"
app_title = "MANASE BUTCHER"
app_publisher = "MANASE BUTCHER"
app_description = "Fish supplier & multi-branch butcher management (KG tracking, processing, branches, mobile orders)"
app_email = "dev@manasebutcher.co.tz"
app_license = "MIT"
required_apps = ["erpnext"]

# Includes in <head>
# ------------------
app_include_css = "/assets/manase_butcher/css/manase_butcher.css"
app_include_js = "/assets/manase_butcher/js/manase_butcher.bundle.js"

doctype_js = {
    "Sales Invoice": "public/js/sales_invoice.js",
    "Item": "public/js/item.js",
    "Warehouse": "public/js/warehouse.js",
}

# page rendering
# page_js = {"point-of-sale": "public/js/point-of-sale.js"}

# Installation / migration
# ------------------------
after_install = "manase_butcher.setup.install.after_install"
after_migrate = "manase_butcher.setup.install.after_migrate"
before_uninstall = "manase_butcher.setup.install.before_uninstall"

# Fixtures
# --------
# Workspaces/Reports/Pages ship as standard module-folder JSON and are synced
# automatically on install/migrate; Workflow approvals are handled in controllers
# (status fields + role-checked on_update_after_submit transitions).
fixtures = []

# Role permission helpers (branch-level data isolation)
# -----------------------------------------------------
permission_query_conditions = {
    "Sales Invoice": "manase_butcher.branch_utils.sales_invoice_query_condition",
    "Sales Order": "manase_butcher.branch_utils.sales_order_query_condition",
    "Purchase Receipt": "manase_butcher.branch_utils.purchase_receipt_query_condition",
    "Payment Entry": "manase_butcher.branch_utils.payment_entry_query_condition",
    "Stock Entry": "manase_butcher.branch_utils.stock_entry_query_condition",
    "Journal Entry": "manase_butcher.branch_utils.journal_entry_query_condition",
    "Stock Reconciliation": "manase_butcher.branch_utils.stock_reconciliation_query_condition",
    # custom fish DocTypes with a direct branch field
    "Customer Order": "manase_butcher.branch_utils.customer_order_query_condition",
    "Fish Waste Record": "manase_butcher.branch_utils.fish_waste_record_query_condition",
    "Fish Expense": "manase_butcher.branch_utils.fish_expense_query_condition",
    "Daily Branch Closing": "manase_butcher.branch_utils.daily_branch_closing_query_condition",
    "Branch Stock Reconciliation": "manase_butcher.branch_utils.branch_stock_reconciliation_query_condition",
    "Fish Stock Transfer": "manase_butcher.branch_utils.fish_stock_transfer_query_condition",
}

has_permission = {
    "Sales Invoice": "manase_butcher.branch_utils.has_sales_invoice_permission",
    "Payment Entry": "manase_butcher.branch_utils.has_branch_doc_permission",
    "Stock Entry": "manase_butcher.branch_utils.has_branch_doc_permission",
}

# Document events
# ---------------
doc_events = {
    "Item Price": {
        "before_insert": "manase_butcher.setup.pricing.before_item_price_insert",
        "on_update": "manase_butcher.setup.pricing.item_price_on_update",
    },
    "Sales Invoice": {
        "validate": "manase_butcher.fish_sales.sales_invoice_hooks.validate_branch_and_kg",
        "on_submit": "manase_butcher.fish_sales.sales_invoice_hooks.on_submit_metrics",
        "on_cancel": "manase_butcher.fish_sales.sales_invoice_hooks.on_cancel_metrics",
    },
    "Customer Order": {
        "on_update": "manase_butcher.fish_sales.doctype.customer_order.customer_order.notify_on_status",
    },
}

# Scheduled tasks
# --------------
scheduler_events = {
    "all": [
        "manase_butcher.fish_mobile.scheduled.release_expired_reservations",
    ],
    "daily": [
        "manase_butcher.fish_sales.scheduled.debt_reminders",
        "manase_butcher.fish_sales.scheduled.daily_closing_reminder",
        "manase_butcher.fish_inventory.scheduled.low_stock_digest",
        "manase_butcher.fish_inventory.scheduled.high_waste_alert",
    ],
}

# Website / API
# -------------
website_route_rules = [
    {"from_route": "/mobile-api/<path:name>", "to_route": "mobile-api"},
]

# Desk branding
# -------------
# default_mail_footer etc intentionally left to site configuration.
