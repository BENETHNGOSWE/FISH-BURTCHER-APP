# -*- coding: utf-8 -*-
"""Branches: list, nearby (Haversine), detail, branch product availability."""
import frappe
from frappe.utils import flt, cint

from ._helpers import begin, param, haversine_km
from manase_butcher.stock_utils import available_kg


def _branch_dict(name, lat=None, lng=None):
    d = frappe.db.get_value("Branch", name,
                            ["name", "branch_name", "branch_code", "branch_phone",
                             "latitude", "longitude", "opening_time", "closing_time",
                             "delivery_radius_km", "warehouse", "is_active"],
                            as_dict=True)
    out = {
        "id": d.name,
        "name": d.branch_name,
        "code": d.branch_code,
        "phone": d.branch_phone,
        "latitude": flt(d.latitude),
        "longitude": flt(d.longitude),
        "opening_time": str(d.opening_time or ""),
        "closing_time": str(d.closing_time or ""),
        "delivery_radius_km": flt(d.delivery_radius_km),
        "open": True,
    }
    if lat is not None and d.latitude and d.longitude:
        out["distance_km"] = haversine_km(lat, lng, d.latitude, d.longitude)
        out["delivery_available"] = (out["distance_km"] <= flt(d.delivery_radius_km))
    return out


@frappe.whitelist(allow_guest=True)
def list_branches():
    frappe.local.flags.in_mobile_api = True
    names = frappe.db.get_all("Branch", filters={"is_active": 1},
                              pluck="name", order_by="branch_name asc")
    return {"ok": True, "data": [_branch_dict(n) for n in names]}


@frappe.whitelist(allow_guest=True)
def nearby():
    frappe.local.flags.in_mobile_api = True
    lat = flt(param("lat"))
    lng = flt(param("lng"))
    radius = flt(param("radius_km"))
    if not lat or not lng:
        frappe.throw("lat and lng are required")
    names = frappe.db.get_all("Branch", filters={"is_active": 1},
                              pluck="name")
    data = [_branch_dict(n, lat, lng) for n in names]
    data = [d for d in data if "distance_km" in d]
    if radius:
        data = [d for d in data if d["distance_km"] <= radius]
    data.sort(key=lambda d: d["distance_km"])
    return {"ok": True, "data": data}


@frappe.whitelist(allow_guest=True)
def get_branch():
    frappe.local.flags.in_mobile_api = True
    branch = param("id") or param("branch")
    data = _branch_dict(branch)
    data["stock_summary"] = _stock_summary(branch)
    return {"ok": True, "data": data}


def _stock_summary(branch):
    warehouse = frappe.db.get_value("Branch", branch, "warehouse")
    if not warehouse:
        return {"fish_lines": 0, "total_kg": 0}
    row = frappe.db.sql(
        """SELECT COUNT(*) lines, COALESCE(SUM(actual_qty-reserved_qty),0) kg
           FROM tabBin WHERE warehouse=%s AND actual_qty-reserved_qty > 0
             AND item_code IN (SELECT name FROM tabItem WHERE custom_mb_sellable=1)""",
        warehouse, as_dict=True)[0]
    return {"fish_lines": row.lines, "total_kg": round(flt(row.kg), 3)}


@frappe.whitelist(allow_guest=True)
def products():
    frappe.local.flags.in_mobile_api = True
    from .products import products_for_branch
    branch = param("id") or param("branch")
    search = param("search")
    category = param("category")
    freshness = param("freshness")
    page = cint(param("page") or 0)
    page_size = min(cint(param("page_size") or 30), 100)
    return {"ok": True, "data": products_for_branch(
        branch, search=search, category=category, freshness=freshness,
        page=page, page_size=page_size)}


@frappe.whitelist()
def set_preferred():
    customer, sess = begin()
    branch = param("branch")
    if not frappe.db.exists("Branch", branch):
        frappe.throw("Unknown branch")
    frappe.db.set_value("Customer", customer, "custom_mb_preferred_branch", branch,
                        update_modified=False)
    return {"ok": True}
