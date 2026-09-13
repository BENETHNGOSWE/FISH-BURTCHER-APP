# -*- coding: utf-8 -*-
"""Branch <-> Warehouse helpers and multi-branch permission enforcement.

Every physical branch has a real ERPNext Warehouse (custom field ``custom_mb_branch``)
and a Cost Center. Access for branch-scoped roles is enforced with:

1. standard User Permission records on Branch / Warehouse / Cost Center;
2. ``permission_query_conditions`` hooks in this module;
3. explicit ``assert_branch_access`` calls in controllers and API methods.
"""
import frappe
from frappe import _

# Roles
ROLE_OWNER = "Business Owner"
ROLE_GM = "General Manager"
ROLE_ACCOUNTANT = "Accountant"
ROLE_INVENTORY = "Inventory Manager"
ROLE_PROCUREMENT = "Procurement Officer"
ROLE_BRANCH_MANAGER = "Branch Manager"
ROLE_SALES = "Sales Staff"
ROLE_CASHIER = "Cashier"
ROLE_PROCESSING = "Processing Staff"
ROLE_WAREHOUSE = "Warehouse Staff"
ROLE_DELIVERY = "Delivery Staff"
ROLE_CUSTOMER = "Customer"

# Roles that see *all* branches for stock documents
STOCK_BYPASS_ROLES = (ROLE_OWNER, ROLE_GM, ROLE_INVENTORY, "System Manager",
                      "Stock Manager", "Administrator")
# Roles that see *all* branches for money documents
MONEY_BYPASS_ROLES = (ROLE_OWNER, ROLE_GM, ROLE_ACCOUNTANT, "System Manager",
                      "Accounts Manager", "Administrator")

ALL_MANAGE_ROLES = (ROLE_OWNER, ROLE_GM, ROLE_INVENTORY, ROLE_ACCOUNTANT,
                    "System Manager", "Administrator")


@frappe.whitelist()
def get_settings():
    """Cached Manase Butcher Settings singleton."""
    return frappe.get_single("Manase Butcher Settings")


def get_user_branches(user=None):
    """Return list of branch names a user is permitted for ([] = no restriction).

    Empty list for bypass users means *all branches*.
    """
    user = user or frappe.session.user
    if user == "Administrator" or frappe.local.flags.in_mobile_api:
        # mobile API enforces ownership separately, not branch visibility
        return []
    roles = set(frappe.get_roles(user))
    if roles & set(ALL_MANAGE_ROLES):
        return []
    vals = frappe.db.get_all(
        "User Permission",
        filters={"user": user, "allow": "Branch", "applicable_for": ["is", "not set"]},
        pluck="for_value",
    )
    return sorted(set(vals))


def has_branch_access(branch, user=None):
    allowed = get_user_branches(user)
    return not allowed or branch in allowed


def assert_branch_access(branch, user=None):
    if branch and not has_branch_access(branch, user):
        frappe.throw(_("You are not authorised for branch {0}").format(branch),
                     frappe.PermissionError)


def get_branch(branch_name):
    return frappe.get_cached_doc("Branch", branch_name)


def get_branch_warehouse(branch_name):
    return frappe.db.get_value("Branch", branch_name, "warehouse")


def get_branch_cost_center(branch_name):
    return frappe.db.get_value("Branch", branch_name, "cost_center")


def branch_for_warehouse(warehouse):
    if not warehouse:
        return None
    return frappe.db.get_value("Warehouse", warehouse, "custom_mb_branch")


# ---------------------------------------------------------------- SQL conditions
def _branch_subquery(user, alias_for_value):
    names = get_user_branches(user)
    if not names:
        return "1=1"
    quoted = ",".join(frappe.db.escape(n) for n in names)
    return f"{alias_for_value} IN ({quoted})"


def _branch_field_condition(fieldname, user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    roles = set(frappe.get_roles(user))
    if roles & set(ALL_MANAGE_ROLES):
        return ""
    names = get_user_branches(user)
    if not names:
        return f"({fieldname} IS NULL OR {fieldname} = '')"
    quoted = ",".join(frappe.db.escape(n) for n in names)
    return f"`{frappe.local.form_dict.doctype or ''}`.name IS NOT NULL AND {fieldname} IN ({quoted})"


def make_branch_field_condition(fieldname, table_alias=None):
    """Build a hook-compatible condition function for a direct branch Link field."""
    def cond(user=None):
        user = user or frappe.session.user
        if user == "Administrator":
            return ""
        roles = set(frappe.get_roles(user))
        if roles & set(ALL_MANAGE_ROLES):
            return ""
        names = get_user_branches(user)
        col = fieldname
        if not names:
            return f"({col} IS NULL OR {col} = '')"
        quoted = ",".join(frappe.db.escape(n) for n in names)
        return f"{col} IN ({quoted})"
    return cond


# direct-branch-field DocTypes
customer_order_query_condition = make_branch_field_condition("`tabCustomer Order`.`branch`")
fish_expense_query_condition = make_branch_field_condition("`tabFish Expense`.`branch`")
fish_waste_record_query_condition = make_branch_field_condition("`tabFish Waste Record`.`branch`")
daily_branch_closing_query_condition = make_branch_field_condition("`tabDaily Branch Closing`.`branch`")
branch_stock_reconciliation_query_condition = make_branch_field_condition("`tabBranch Stock Reconciliation`.`branch`")


def fish_stock_transfer_query_condition(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    roles = set(frappe.get_roles(user))
    if roles & set(ALL_MANAGE_ROLES):
        return ""
    names = get_user_branches(user)
    if not names:
        return "(`tabFish Stock Transfer`.`target_branch` IS NULL)"
    quoted = ",".join(frappe.db.escape(n) for n in names)
    return (f"(`tabFish Stock Transfer`.`target_branch` IN ({quoted}) OR "
            f"`tabFish Stock Transfer`.`source_branch` IN ({quoted}))")


def _warehouse_via_child_condition(parent_table, parent_field, child_table, user):
    """Condition for docs whose warehouse lives on child rows."""
    if user == "Administrator":
        return ""
    roles = set(frappe.get_roles(user))
    if roles & set(STOCK_BYPASS_ROLES) or roles & set(MONEY_BYPASS_ROLES):
        return ""
    names = get_user_branches(user)
    if not names:
        return "1=0"
    quoted = ",".join(frappe.db.escape(n) for n in names)
    return (f"EXISTS (SELECT 1 FROM `{child_table}` c "
            f"JOIN `tabWarehouse` w ON w.name = c.warehouse "
            f"WHERE c.{parent_field} = `{parent_table}`.name "
            f"AND w.custom_mb_branch IN ({quoted}))")


def sales_invoice_query_condition(user=None):
    user = user or frappe.session.user
    if user == "Administrator" or (set(frappe.get_roles(user)) & set(MONEY_BYPASS_ROLES)):
        return ""
    return (f"`tabSales Invoice`.`custom_mb_branch` IS NOT NULL AND "
            + _branch_subquery(user, "`tabSales Invoice`.`custom_mb_branch`")
            if get_user_branches(user) else "")


def sales_order_query_condition(user=None):
    user = user or frappe.session.user
    if user == "Administrator" or (set(frappe.get_roles(user)) & set(STOCK_BYPASS_ROLES)):
        return ""
    names = get_user_branches(user)
    if not names:
        return "(`tabSales Order`.name IS NULL)"
    return _warehouse_via_child_condition(
        "tabSales Order", "parent", "tabSales Order Item", user)


def purchase_receipt_query_condition(user=None):
    user = user or frappe.session.user
    if user == "Administrator" or (set(frappe.get_roles(user)) & set(STOCK_BYPASS_ROLES)):
        return ""
    names = get_user_branches(user)
    if not names:
        # central receiving - procurement/warehouse at HO; branch roles see nothing here
        return "1=0"
    return _warehouse_via_child_condition(
        "tabPurchase Receipt", "parent", "tabPurchase Receipt Item", user)


def stock_entry_query_condition(user=None):
    user = user or frappe.session.user
    if user == "Administrator" or (set(frappe.get_roles(user)) & set(STOCK_BYPASS_ROLES)):
        return ""
    names = get_user_branches(user)
    if not names:
        return "(`tabStock Entry`.`custom_mb_branch` IS NULL OR `tabStock Entry`.`custom_mb_branch` = '')"
    quoted = ",".join(frappe.db.escape(n) for n in names)
    return (f"(`tabStock Entry`.`custom_mb_branch` IN ({quoted}) OR "
            f"`tabStock Entry`.`custom_mb_branch` IS NULL OR `tabStock Entry`.`custom_mb_branch` = '')")


def payment_entry_query_condition(user=None):
    user = user or frappe.session.user
    if user == "Administrator" or (set(frappe.get_roles(user)) & set(MONEY_BYPASS_ROLES)):
        return ""
    names = get_user_branches(user)
    if not names:
        return "(`tabPayment Entry`.`custom_mb_branch` IS NULL OR `tabPayment Entry`.`custom_mb_branch`='')"
    quoted = ",".join(frappe.db.escape(n) for n in names)
    return (f"(`tabPayment Entry`.`custom_mb_branch` IN ({quoted}) OR "
            f"`tabPayment Entry`.`custom_mb_branch` IS NULL OR `tabPayment Entry`.`custom_mb_branch`='')")


def journal_entry_query_condition(user=None):
    user = user or frappe.session.user
    if user == "Administrator" or (set(frappe.get_roles(user)) & set(MONEY_BYPASS_ROLES)):
        return ""
    names = get_user_branches(user)
    if not names:
        return ("(`tabJournal Entry`.name IN (SELECT parent FROM `tabJournal Entry Account` "
                "WHERE cost_center IS NULL OR cost_center=''))")
    quoted = ",".join(frappe.db.escape(n) for n in names)
    return (f"EXISTS (SELECT 1 FROM `tabJournal Entry Account` ja "
            f"JOIN `tabCost Center` cc ON cc.name = ja.cost_center "
            f"JOIN `tabBranch` b ON b.cost_center = cc.name "
            f"WHERE ja.parent = `tabJournal Entry`.name AND b.name IN ({quoted}))")


def stock_reconciliation_query_condition(user=None):
    return stock_entry_query_condition(user)


# ---------------------------------------------------------------- has_permission
def _doc_branch(doc):
    if hasattr(doc, "branch") and doc.branch:
        return doc.branch
    if hasattr(doc, "target_branch") and doc.target_branch:
        return doc.target_branch
    if hasattr(doc, "custom_mb_branch"):
        return doc.custom_mb_branch
    return None


def has_branch_doc_permission(doc, ptype="read", user=None):
    branch = _doc_branch(doc)
    if not branch:
        return None  # neutral - fall back to standard role check
    return has_branch_access(branch, user)


def has_sales_invoice_permission(doc, ptype="read", user=None):
    return has_branch_doc_permission(doc, ptype, user)
