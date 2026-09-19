# -*- coding: utf-8 -*-
"""Idempotent provisioning for MANASE BUTCHER.

after_install: roles, UOMs, item groups, warehouse tree, cost centers,
accounts, modes of payment, price lists, default branches, settings.
after_migrate : roles + custom fields + structural records (safe to repeat).
"""
import json
from pathlib import Path

import frappe
from frappe.utils import nowtime, today

from manase_butcher.setup.custom_fields import setup_custom_fields

ROLES = [
    ("Business Owner", "Full access to MANASE BUTCHER"),
    ("General Manager", "All branches, operations and finance"),
    ("Accountant", "Payments, expenses, credit and financial reports"),
    ("Inventory Manager", "Receiving, processing, transfers, waste, reconciliation"),
    ("Procurement Officer", "Suppliers and fish receiving"),
    ("Branch Manager", "Own branch operations and approvals"),
    ("Sales Staff", "POS and mobile order processing"),
    ("Cashier", "POS and daily counts"),
    ("Processing Staff", "Fish processing and processing waste"),
    ("Warehouse Staff", "Receiving, dispatch, transfers and counts"),
    ("Delivery Staff", "Delivery status updates"),
    ("Customer", "Mobile customer - no desk access"),
]

ITEM_GROUPS = {
    "Fish": {
        "Fresh Fish": {},
        "Frozen Fish": {},
        "Processed Fish": {"Cleaned": {}, "Fillet": {}, "Steaks and Cuts": {}, "Other Products": {}},
        "Fish Waste": {},
    },
    "Packaging": {},
    "Services": {},
}

DEFAULT_BRANCHES = ["Masaki", "Mikocheni", "Sinza", "Kariakoo"]

CENTRAL_WAREHOUSES = [
    ("Central Fish Warehouse", "group", None),
    ("Central Raw Fish", "Central Raw", "Central Fish Warehouse"),
    ("Central Processed Fish", "Central Processed", "Central Fish Warehouse"),
    ("Fish Processing Floor", "Processing", "Central Fish Warehouse"),
    ("Fish Waste", "Waste", "Central Fish Warehouse"),
    ("Fish In-Transit", "Transit", "Central Fish Warehouse"),
]

EXPENSE_CATEGORIES = [
    "Rent", "Transport", "Fuel", "Electricity", "Water",
    "Packaging", "Maintenance", "Staff Meals", "Other",
]


# ------------------------------------------------------------------ entry points
def after_install(*args, **kwargs):
    try:
        _ensure_roles()
        _ensure_uoms()
        _ensure_item_groups()
        # Custom fields must exist before provisioning records that use them.
        setup_custom_fields()
        _ensure_warehouse_types()
        company = _default_company()
        if company:
            _ensure_company_structure(company)
            _ensure_default_branches(company)
            _configure_settings(company)
        _sync_workspaces()
        _ensure_desktop_icon()
        try:
            from manase_butcher.setup.number_cards import setup_number_cards
            setup_number_cards()
        except Exception:
            frappe.log_error(title="Number cards setup failed", message=frappe.get_traceback())
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="MANASE after_install failed", message=frappe.get_traceback())
        raise


def after_migrate(*args, **kwargs):
    _ensure_roles()
    setup_custom_fields()
    _ensure_warehouse_types()
    company = _default_company()
    if company and not frappe.db.get_value("Warehouse",
                                           {"mb_warehouse_kind": "Central Raw"}):
        _ensure_company_structure(company)
    _sync_workspaces()
    _ensure_desktop_icon()
    try:
        from manase_butcher.setup.number_cards import setup_number_cards
        setup_number_cards()
    except Exception:
        frappe.log_error(title="Number cards setup failed", message=frappe.get_traceback())
    frappe.db.commit()


def _ensure_desktop_icon():
    """Add/update MANASE BUTCHER in the Frappe v16 home launcher."""
    values = {
        "label": "MANASE BUTCHER",
        "icon_type": "App",
        "link_type": "External",
        "link_to": None,
        "parent_icon": "",
        "standard": 1,
        "app": "manase_butcher",
        "icon": "fish",
        "link": "/desk/manase-butcher",
        "hidden": 0,
        "restrict_removal": 0,
        "bg_color": "blue",
    }
    if frappe.db.exists("Desktop Icon", "MANASE BUTCHER"):
        doc = frappe.get_doc("Desktop Icon", "MANASE BUTCHER")
        doc.update(values)
        doc.flags.ignore_permissions = True
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({"doctype": "Desktop Icon", **values})
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)


def _sync_workspaces():
    """Provision MANASE workspaces using Frappe v16-valid shortcut rows."""
    root = Path(__file__).resolve().parents[1] / "workspace"
    if not root.exists():
        return
    custom_names = {
        "MANASE BUTCHER", "Fish Inventory", "Fish Sales", "Fish Settings",
        "Fish Purchases", "Fish Reports", "Branches",
    }
    for path in sorted(root.glob("*/*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            name = data.get("name")
            if not name or name not in custom_names:
                continue

            if frappe.db.exists("Workspace", name):
                doc = frappe.get_doc("Workspace", name)
            else:
                doc = frappe.get_doc(data)

            # Frappe v16 validates Workspace Link.type as Link/Card Break and
            # validates every target. Keep only currently valid links and use
            # an empty content/number-card layout until the links are saved.
            valid_links = []
            for link in data.get("links", []):
                link_type = link.get("link_type") or "DocType"
                target = link.get("link_to")
                if not target or link_type not in {"DocType", "Report", "Page", "Dashboard"}:
                    continue
                if not frappe.db.exists(link_type, target):
                    continue
                row = dict(link)
                row["type"] = "Link"
                valid_links.append(row)

            doc.set("links", [])
            for row in valid_links:
                doc.append("links", row)

            # Workspace 2.0 layout: content blocks must have matching
            # Workspace Shortcut child rows for Frappe v16 to render them.
            doc.set("shortcuts", [])
            for shortcut in data.get("shortcuts", []):
                target = shortcut.get("link_to")
                link_type = shortcut.get("link_type") or "DocType"
                if target and frappe.db.exists(link_type, target):
                    row = dict(shortcut)
                    row.pop("col", None)
                    doc.append("shortcuts", row)
            doc.set("content", data.get("content", "[]"))
            doc.set("number_cards", [])
            doc.flags.ignore_permissions = True
            if doc.is_new():
                doc.insert(ignore_permissions=True)
            else:
                doc.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(title=f"Workspace sync failed: {path.name}",
                             message=frappe.get_traceback())


def before_uninstall(*args, **kwargs):
    frappe.log_error(title="MANASE BUTCHER uninstalled", message="No data removed automatically")


# ------------------------------------------------------------------ roles
def _ensure_roles():
    for role, desc in ROLES:
        if frappe.db.exists("Role", role):
            continue
        doc = frappe.new_doc("Role")
        doc.role_name = role
        doc.desk_access = 0 if role == "Customer" else 1
        doc.restrict_to_domain = None
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)


# ------------------------------------------------------------------ basics
def _default_company():
    name = frappe.db.get_single_value("Global Defaults", "default_company")
    if name:
        return name
    names = frappe.db.get_all("Company", pluck="name", limit=1)
    return names[0] if names else None


def _ensure_uoms():
    for uom in ("Kg", "Piece", "Box", "Crate", "Litre"):
        if not frappe.db.exists("UOM", uom):
            try:
                frappe.get_doc({"doctype": "UOM", "uom_name": uom,
                                "must_be_whole_number": 0}).insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(title=f"UOM {uom} failed", message=frappe.get_traceback())
    if frappe.db.exists("UOM", "Kg"):
        frappe.db.set_value("UOM", "Kg", "must_be_whole_number", 0, update_modified=False)


def _ensure_item_groups():
    def make(name, parent=None):
        if frappe.db.exists("Item Group", name):
            return
        try:
            d = frappe.new_doc("Item Group")
            d.item_group_name = name
            d.parent_item_group = parent or "All Item Groups"
            d.flags.ignore_permissions = True
            d.insert()
        except Exception:
            frappe.log_error(title=f"Item group {name} failed", message=frappe.get_traceback())

    for top, children in ITEM_GROUPS.items():
        make(top)
        for child, grandchildren in children.items():
            make(child, top)
            for gc in grandchildren:
                make(gc, child)


def _ensure_warehouse_types():
    for t in ("Transit", "Processing", "Goods"):
        if not frappe.db.exists("Warehouse Type", t):
            try:
                frappe.get_doc({"doctype": "Warehouse Type", "name": t}
                              ).insert(ignore_permissions=True)
            except Exception:
                pass


# ------------------------------------------------------------------ company structure
def _abbr(company):
    return (frappe.db.get_value("Company", company, "abbr") or "MB").strip()


def _parent_warehouse(company, abbr):
    return (frappe.db.get_value("Warehouse",
            {"company": company, "is_group": 1, "warehouse_name": ["like", "%All Warehouses%"]})
            or f"All Warehouses - {abbr}")


def _ensure_warehouse(company, abbr, base_name, kind, parent_base, wtype=None):
    full = f"{base_name} - {abbr}"
    if frappe.db.exists("Warehouse", full):
        return full
    parent_full = f"{parent_base} - {abbr}" if parent_base else _parent_warehouse(company, abbr)
    try:
        d = frappe.new_doc("Warehouse")
        d.warehouse_name = base_name
        d.company = company
        d.parent_warehouse = parent_full
        d.is_group = 1 if kind == "group" else 0
        d.warehouse_type = wtype or ("Transit" if kind == "Transit" else "Goods")
        d.mb_warehouse_kind = kind if kind != "group" else None
        d.flags.ignore_permissions = True
        d.insert()
        return d.name
    except Exception:
        frappe.log_error(title=f"Warehouse {full} failed", message=frappe.get_traceback())
        return full


def _ensure_company_structure(company):
    abbr = _abbr(company)
    # cost centers
    parent_cc = frappe.db.get_value("Company", company, "cost_center") or f"Main - {abbr}"
    for cc in ("Central Operations",):
        name = f"{cc} - {abbr}"
        if not frappe.db.exists("Cost Center", name):
            try:
                frappe.get_doc({"doctype": "Cost Center", "cost_center_name": cc,
                                "company": company,
                                "parent_cost_center": parent_cc, "is_group": 0}
                              ).insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(title=f"CC {name} failed", message=frappe.get_traceback())
    # central warehouses
    for base, kind, parent_base in CENTRAL_WAREHOUSES:
        _ensure_warehouse(company, abbr, base, kind, parent_base)
    # accounts
    acc = {}
    acc["waste"] = _ensure_account(company, abbr, "Fish Waste and Losses",
                                    ["Stock Expenses", "Expenses Included In Valuation",
                                     "Indirect Expenses", "Expenses"])
    acc["adj"] = _ensure_account(company, abbr, "Fish Stock Adjustments",
                                  ["Stock Adjustments", "Stock Expenses", "Indirect Expenses",
                                   "Expenses"])
    acc["short"] = _ensure_account(company, abbr, "Cash Over and Short",
                                    ["Indirect Expenses", "Expenses"])
    acc["delivery"] = _ensure_account(company, abbr, "Delivery Income",
                                      ["Sales", "Direct Income", "Income"])
    acc["cogs"] = _find_account(company, ["Cost of Goods Sold", "COGS"])
    # mobile wallet cash accounts
    wallets = {}
    for provider in ("M-Pesa", "Tigo Pesa", "Airtel Money", "HaloPesa"):
        wallets[provider] = _ensure_account(company, abbr, f"{provider} Wallet",
                                             ["Cash and Cash Equivalents", "Cash", "Current Assets",
                                              "Assets"], account_type="Cash")
    # cash account per HQ
    hq_cash = _find_account(company, ["Cash"])
    # modes of payment
    modes = {
        "Cash": hq_cash,
        "M-Pesa": wallets.get("M-Pesa"),
        "Tigo Pesa": wallets.get("Tigo Pesa"),
        "Airtel Money": wallets.get("Airtel Money"),
        "HaloPesa": wallets.get("HaloPesa"),
        "Bank": _find_account(company, ["Bank Accounts", "Bank"]),
        "Card": _find_account(company, ["Bank Accounts", "Cash and Cash Equivalents", "Cash"]),
        "Credit": None,
    }
    for mode, account in modes.items():
        _ensure_mode_of_payment(company, mode, account)
    # price lists
    for pl in ("Wholesale Selling", "Restaurant Selling", "Hotel Selling"):
        _ensure_price_list(pl)
    return acc, wallets


def _find_account(company, name_candidates):
    for n in name_candidates:
        found = frappe.db.get_value("Account",
                                    {"company": company, "account_name": ["like", f"%{n}%"]},
                                    "name", order_by="lft asc")
        if found:
            return found
    return None


def _ensure_account(company, abbr, account_name, parent_candidates, account_type=None):
    full = f"{account_name} - {abbr}"
    if frappe.db.exists("Account", full):
        return full
    parent = None
    for n in parent_candidates:
        parent = frappe.db.get_value("Account",
                                     {"company": company, "account_name": ["like", f"%{n}%"],
                                      "is_group": 0}, "name")
        if not parent:
            parent = frappe.db.get_value("Account",
                                         {"company": company, "account_name": ["like", f"%{n}%"]},
                                         "name", order_by="lft asc")
        if parent:
            break
    if not parent:
        return None
    try:
        d = frappe.new_doc("Account")
        d.account_name = account_name
        d.company = company
        d.parent_account = parent
        if account_type:
            d.account_type = account_type
        d.flags.ignore_permissions = True
        d.insert()
        return d.name
    except Exception:
        frappe.log_error(title=f"Account {full} failed", message=frappe.get_traceback())
        return None


def _ensure_mode_of_payment(company, mode, account):
    if not frappe.db.exists("Mode of Payment", mode):
        try:
            d = frappe.new_doc("Mode of Payment")
            d.mode_of_payment = mode
            d.type = "Cash" if mode in ("Cash",) else (
                "General" if mode == "Credit" else "Bank")
            if account:
                d.append("accounts", {"company": company, "default_account": account})
            d.flags.ignore_permissions = True
            d.insert()
        except Exception:
            frappe.log_error(title=f"MoP {mode} failed", message=frappe.get_traceback())
    elif account:
        doc = frappe.get_doc("Mode of Payment", mode)
        if not any(r.company == company for r in doc.accounts):
            doc.append("accounts", {"company": company, "default_account": account})
            doc.flags.ignore_permissions = True
            doc.save()


def _ensure_price_list(name):
    if frappe.db.exists("Price List", name):
        return name
    try:
        d = frappe.new_doc("Price List")
        d.price_list_name = name
        d.selling = 1
        d.buying = 0
        d.enabled = 1
        d.flags.ignore_permissions = True
        d.insert()
        return d.name
    except Exception:
        frappe.log_error(title=f"Price list {name} failed", message=frappe.get_traceback())


# ------------------------------------------------------------------ branches
def _ensure_default_branches(company):
    from manase_butcher.branch_utils import get_settings  # noqa
    for name in DEFAULT_BRANCHES:
        if frappe.db.exists("Branch", {"branch_name": name}):
            continue
        try:
            d = frappe.new_doc("Branch")
            d.branch_name = name
            d.branch_code = name[:4].upper()
            d.company = company
            d.is_active = 1
            d.delivery_radius_km = 10
            d.flags.ignore_permissions = True
            d.insert()
        except Exception:
            frappe.log_error(title=f"Branch {name} failed", message=frappe.get_traceback())


# ------------------------------------------------------------------ settings
def _configure_settings(company):
    s = frappe.get_single("Manase Butcher Settings")
    abbr = _abbr(company)
    s.company = company

    def wh(kind):
        return frappe.db.get_value("Warehouse",
                                   {"company": company, "mb_warehouse_kind": kind}, "name")

    s.central_raw_warehouse = wh("Central Raw")
    s.central_processed_warehouse = wh("Central Processed")
    s.processing_warehouse = wh("Processing")
    s.waste_warehouse = wh("Waste")
    s.transit_warehouse = wh("Transit")
    s.default_cost_center = frappe.db.get_value("Company", company, "cost_center")
    s.waste_expense_account = s.waste_expense_account or _find_account(
        company, ["Fish Waste and Losses", "Stock Expenses", "Indirect Expenses"])
    s.stock_adjustment_account = s.stock_adjustment_account or _find_account(
        company, ["Fish Stock Adjustments", "Stock Adjustment", "Stock Expenses"])
    s.cash_over_short_account = s.cash_over_short_account or _find_account(
        company, ["Cash Over and Short", "Indirect Expenses"])
    s.delivery_income_account = s.delivery_income_account or _find_account(
        company, ["Delivery Income", "Sales"])
    s.fish_cogs_account = s.fish_cogs_account or _find_account(company, ["Cost of Goods Sold"])
    s.default_currency = frappe.db.get_value("Company", company, "default_currency") or "TZS"
    s.retail_price_list = s.retail_price_list or "Standard Selling"
    s.wholesale_price_list = s.wholesale_price_list or "Wholesale Selling"
    s.restaurant_price_list = s.restaurant_price_list or "Restaurant Selling"
    s.hotel_price_list = s.hotel_price_list or "Hotel Selling"
    existing = {(r.provider) for r in s.mobile_payment_accounts}
    for provider in ("M-Pesa", "Tigo Pesa", "Airtel Money", "HaloPesa"):
        if provider in existing:
            continue
        account = frappe.db.get_value("Account",
                                      {"company": company,
                                       "account_name": ["like", f"%{provider} Wallet%"]}, "name")
        if frappe.db.exists("Mode of Payment", provider) and account:
            s.append("mobile_payment_accounts", {
                "provider": provider, "mode_of_payment": provider, "account": account})
    s.flags.ignore_permissions = True
    s.save(ignore_permissions=True)
