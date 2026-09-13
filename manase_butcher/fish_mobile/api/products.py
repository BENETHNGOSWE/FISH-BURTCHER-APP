# -*- coding: utf-8 -*-
"""Product catalog - availability comes ONLY from the selected branch warehouse."""
import frappe
from frappe.utils import flt, cint

from manase_butcher.stock_utils import available_kg
from manase_butcher.setup.pricing import resolve_price
from ._helpers import begin, param


LOW_STOCK_KG = 2.0


def _branch_warehouse(branch):
    wh = frappe.db.get_value("Branch", branch, "warehouse")
    if not wh:
        frappe.throw("Branch warehouse not configured")
    return wh


def products_for_branch(branch, search=None, category=None, freshness=None,
                        page=0, page_size=30, include_out_of_stock=True):
    warehouse = _branch_warehouse(branch)
    conds = ["i.disabled = 0", "i.custom_mb_sellable = 1", "i.is_sales_item = 1"]
    values = []
    if search:
        like = f"%{search}%"
        conds.append("(i.item_name LIKE %s OR i.description LIKE %s)")
        values += [like, like]
    if freshness:
        conds.append("i.custom_mb_freshness = %s")
        values.append(freshness)
    if category:
        conds.append("(i.custom_mb_fish_category = %s OR i.item_group = %s)")
        values += [category, category]
    where = " AND ".join(conds)
    limit = page * page_size
    rows = frappe.db.sql(
        f"""SELECT i.name, i.item_name, i.image, i.stock_uom,
                   i.custom_mb_species AS species, i.custom_mb_fish_category AS category,
                   i.custom_mb_grade AS grade, i.custom_mb_size AS size,
                   i.custom_mb_freshness AS freshness, i.custom_mb_preparation AS preparation,
                   b.actual_qty, b.reserved_qty,
                   COALESCE(b.actual_qty,0)-COALESCE(b.reserved_qty,0)
                       -COALESCE(b.custom_mb_custom_reserved_kg,0) AS available
            FROM tabItem i
            LEFT JOIN tabBin b ON b.item_code=i.name AND b.warehouse=%s
            WHERE {where}
            ORDER BY available DESC, i.item_name ASC
            LIMIT %s, %s""",
        tuple([warehouse] + values + [limit, page_size]), as_dict=True)
    items = []
    for r in rows:
        available = round(flt(r.available), 3)
        if available <= 0 and not include_out_of_stock:
            continue
        price = resolve_price(r.name, branch, "Retail")
        items.append({
            "item": r.name,
            "name": r.item_name,
            "image": r.image,
            "uom": r.stock_uom or "Kg",
            "species": r.species,
            "category": r.category,
            "grade": r.grade,
            "size": r.size,
            "freshness": r.freshness,
            "preparation": r.preparation,
            "price_per_kg": price,
            "currency": "TZS",
            "available_kg": max(0, available),
            "status": ("in_stock" if available > LOW_STOCK_KG else
                       ("low_stock" if available > 0 else "out_of_stock")),
        })
    return {"branch": branch, "warehouse": warehouse, "page": page,
            "page_size": page_size, "items": items}


@frappe.whitelist(allow_guest=False)
def list_products():
    begin()
    branch = param("branch")
    if not branch:
        frappe.throw("branch is required")
    data = products_for_branch(
        branch, search=param("search"), category=param("category"),
        freshness=param("freshness"), page=cint(param("page") or 0),
        page_size=min(cint(param("page_size") or 30, 100), 100))
    return {"ok": True, "data": data}


@frappe.whitelist(allow_guest=False)
def get_product():
    begin()
    item, branch = param("id"), param("branch")
    warehouse = _branch_warehouse(branch)
    d = frappe.db.get_value("Item", item,
                            ["name", "item_name", "description", "image", "stock_uom",
                             "custom_mb_species", "custom_mb_grade", "custom_mb_freshness",
                             "custom_mb_preparation"], as_dict=True)
    if not d:
        frappe.throw("Unknown product")
    available = available_kg(item, warehouse)
    return {"ok": True, "data": {
        "item": d.name, "name": d.item_name, "description": d.description,
        "image": d.image, "uom": d.stock_uom or "Kg",
        "species": d.custom_mb_species, "grade": d.custom_mb_grade,
        "freshness": d.custom_mb_freshness, "preparation": d.custom_mb_preparation,
        "price_per_kg": resolve_price(item, branch, "Retail"), "currency": "TZS",
        "available_kg": max(0, available),
        "status": ("in_stock" if available > LOW_STOCK_KG else
                   ("low_stock" if available > 0 else "out_of_stock")),
        "branch": branch,
    }}


@frappe.whitelist(allow_guest=False)
def availability():
    begin()
    branch = param("branch")
    warehouse = _branch_warehouse(branch)
    items = param("items") or ""
    items = [i for i in str(items).split(",") if i]
    if not items and param("item"):
        items = [param("item")]
    out = {i: {"available_kg": max(0, available_kg(i, warehouse))} for i in items}
    return {"ok": True, "data": {"branch": branch, "warehouse": warehouse, "items": out}}
