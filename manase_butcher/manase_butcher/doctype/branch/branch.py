# -*- coding: utf-8 -*-
# Copyright (c) 2026 MANASE BUTCHER
import frappe
from frappe import _
from frappe.model.document import Document


class Branch(Document):
    def validate(self):
        self.branch_code = (self.branch_code or "").strip().upper()
        if not self.company:
            self.company = (
                frappe.db.get_single_value("Manase Butcher Settings", "company")
                or frappe.defaults.get_user_default("Company")
            )
        self.warehouse = self._ensure_warehouse()
        self.cost_center = self._ensure_cost_center()

    def after_insert(self):
        frappe.get_doc("Manase Butcher Settings")  # ensure settings exist
        self._grant_manager_permission()

    def on_update(self):
        self._grant_manager_permission()
        if self.warehouse:
            frappe.db.set_value("Warehouse", self.warehouse, {
                "mb_branch": self.name,
                "mb_warehouse_kind": "Branch",
            }, update_modified=False)
        # branch -> cost center link is maintained via Branch.cost_center field
        # (and User Permissions); no custom column on Cost Center is required.

    def _abbr(self):
        abbr = frappe.db.get_value("Company", self.company, "abbr") or "MB"
        return abbr.strip()

    def _parent_warehouse(self, abbr):
        existing = frappe.db.get_value(
            "Warehouse",
            {"company": self.company, "is_group": 1,
             "warehouse_name": ["like", "%All Warehouses%"]}, "name")
        return existing or f"All Warehouses - {abbr}"

    def _ensure_warehouse(self):
        if self.warehouse and frappe.db.exists("Warehouse", self.warehouse):
            return self.warehouse
        abbr = self._abbr()
        wh_name = f"{self.branch_name.strip()} Warehouse - {abbr}"
        existing = frappe.db.get_value("Warehouse",
                                      {"warehouse_name": f"{self.branch_name.strip()} Warehouse",
                                       "company": self.company})
        if existing:
            return existing
        try:
            wh = frappe.get_doc({
                "doctype": "Warehouse",
                "warehouse_name": f"{self.branch_name.strip()} Warehouse",
                "company": self.company,
                "parent_warehouse": self._parent_warehouse(abbr),
                "warehouse_type": self._warehouse_type("Goods"),
                # A new Branch is not in the database until after validation;
                # assigning its Link here fails link validation. on_update()
                # stamps mb_branch after the Branch row exists.
                "mb_warehouse_kind": "Branch",
            })
            wh.flags.ignore_permissions = True
            wh.insert()
            return wh.name
        except Exception:
            frappe.log_error(title="Branch warehouse create failed",
                             message=frappe.get_traceback())
            return self.warehouse

    def _warehouse_type(self, name):
        if frappe.db.exists("Warehouse Type", name):
            return name
        try:
            d = frappe.get_doc({"doctype": "Warehouse Type", "name": name})
            d.flags.ignore_permissions = True
            d.insert()
        except Exception:
            pass
        return name

    def _ensure_cost_center(self):
        if self.cost_center and frappe.db.exists("Cost Center", self.cost_center):
            return self.cost_center
        parent = frappe.db.get_value("Company", self.company, "cost_center")
        # A Company may reference a leaf Cost Center in older/test databases.
        # Branch Cost Centers must always be children of a group node.
        if not parent or not frappe.db.get_value("Cost Center", parent, "is_group"):
            parent = frappe.db.get_value(
                "Cost Center",
                {"company": self.company, "is_group": 1},
                "name", order_by="lft asc")
        if not parent:
            frappe.throw(_("Create a group Cost Center for {0} before creating branches").format(self.company))
        cc_name = f"{self.branch_name.strip()} - {self._abbr()}"
        existing = frappe.db.get_value("Cost Center", {"cost_center_name": self.branch_name.strip(),
                                                       "company": self.company})
        if existing:
            return existing
        try:
            cc = frappe.get_doc({
                "doctype": "Cost Center",
                "cost_center_name": self.branch_name.strip(),
                "company": self.company,
                "parent_cost_center": parent,
                "is_group": 0,
            })
            cc.flags.ignore_permissions = True
            cc.insert()
            return cc.name
        except Exception:
            frappe.log_error(title="Branch cost center create failed",
                             message=frappe.get_traceback())
            return self.cost_center

    def _grant_manager_permission(self):
        if not self.manager:
            return
        from manase_butcher.branch_utils import get_branch_warehouse, get_branch_cost_center
        for dt, value in (
            ("Branch", self.name),
            ("Warehouse", get_branch_warehouse(self.name)),
            ("Cost Center", get_branch_cost_center(self.name)),
        ):
            if not value:
                continue
            if not frappe.db.exists("User Permission",
                                   {"user": self.manager, "allow": dt, "for_value": value}):
                try:
                    perm = frappe.get_doc({
                        "doctype": "User Permission",
                        "user": self.manager, "allow": dt, "for_value": value,
                        "apply_to_all_doctypes": 1,
                    })
                    perm.flags.ignore_permissions = True
                    perm.insert(ignore_permissions=True)
                except Exception:
                    frappe.log_error(title="Manager user permission failed",
                                     message=frappe.get_traceback())
