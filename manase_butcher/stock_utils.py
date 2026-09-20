# -*- coding: utf-8 -*-
"""KG / stock helpers: availability, reservations and Stock Entry construction.

KG is the stock UOM, so every standard ledger row is already a KG movement.
These helpers keep the custom front-end documents consistent with that ledger.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime, cint, flt

from manase_butcher.branch_utils import get_settings, get_branch_warehouse


# ---------------------------------------------------------------- availability
def get_bin_qty(item_code, warehouse):
    row = frappe.db.get_value(
        "Bin",
        {"item_code": item_code, "warehouse": warehouse},
        ("actual_qty", "reserved_qty", "ordered_qty", "projected_qty",
         "mb_custom_reserved_kg"),
        as_dict=True,
    )
    if not row:
        return {"actual_qty": 0, "reserved_qty": 0, "ordered_qty": 0,
                "projected_qty": 0, "custom_reserved_kg": 0}
    return row


def available_kg(item_code, warehouse):
    """Sellable KG in a branch warehouse: actual - standard reservations - custom fallback."""
    b = get_bin_qty(item_code, warehouse)
    available = flt(b.actual_qty) - flt(b.reserved_qty) - flt(b.get("custom_reserved_kg") or 0)
    return round(available, 3)


def assert_kg_available(item_code, warehouse, kg, ignore_on_hand=False):
    kg = flt(kg)
    if kg <= 0:
        frappe.throw(_("Quantity (KG) must be greater than zero"))
    avail = available_kg(item_code, warehouse)
    if not ignore_on_hand and avail + 1e-9 < kg:
        frappe.throw(
            _("Insufficient stock for {0} at {1}: requested {2} KG, available {3} KG").format(
                item_code, warehouse, kg, avail),
            exc=frappe.ValidationError,
            title=_("Insufficient KG"),
        )
    return avail


def get_valuation_rate(item_code, warehouse):
    rate = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse},
                               "valuation_rate")
    if not rate:
        rate = frappe.db.get_value("Item", item_code, "valuation_rate")
    return flt(rate) or 0


# ---------------------------------------------------------------- stock entries
def _se_item(args):
    row = {
        "item_code": args.get("item"),
        "qty": abs(flt(args.get("qty"))),
        "uom": args.get("uom") or "Kg",
        "conversion_factor": 1,
        "stock_uom": args.get("uom") or "Kg",
        "basic_rate": flt(args.get("rate")) or 0,
    }
    if args.get("s_warehouse"):
        row["s_warehouse"] = args["s_warehouse"]
    if args.get("t_warehouse"):
        row["t_warehouse"] = args["t_warehouse"]
    if args.get("batch_no"):
        row["batch_no"] = args["batch_no"]
    if args.get("expense_account"):
        row["expense_account"] = args["expense_account"]
    if args.get("cost_center"):
        row["cost_center"] = args["cost_center"]
    if args.get("serial_no"):
        row["serial_no"] = args["serial_no"]
    if args.get("allow_zero_valuation_rate"):
        row["allow_zero_valuation_rate"] = 1
    if args.get("is_finished_item"):
        row["is_finished_item"] = 1
    return row


def make_stock_entry(purpose, items, company=None, posting_date=None, posting_time=None,
                     branch=None, from_doctype=None, from_docname=None, stage=None,
                     additional_costs=None, stock_entry_type=None, set_basic_rate=True,
                     submit=True):
    """Create (and optionally submit) a Stock Entry.

    :param purpose: Material Receipt/Transfer/Issue/Consume/Manufacture
    :param items: list of dicts item, qty (signed by s_/t_ warehouse), rate, batch_no ...
    """
    settings = get_settings()
    company = company or settings.company
    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = stock_entry_type or _default_entry_type(purpose)
    se.purpose = purpose
    se.company = company
    se.posting_date = posting_date or frappe.utils.today()
    se.posting_time = posting_time or frappe.utils.nowtime()
    se.set("items", [])
    for args in items:
        row = _se_item(args)
        if set_basic_rate and not row.get("basic_rate") and row.get("s_warehouse"):
            row["basic_rate"] = get_valuation_rate(args["item"], args["s_warehouse"])
        se.append("items", row)
    if branch:
        se.mb_branch = branch
    if from_doctype and from_docname:
        se.mb_stage = stage
    if stage:
        se.mb_stage = stage
    if additional_costs:
        for c in additional_costs:
            se.append("additional_costs", {
                "expense_account": c.get("expense_account"),
                "description": c.get("description"),
                "amount": flt(c.get("amount")),
            })
    finished_qty = sum(flt(a.get("qty")) for a in items if a.get("is_finished_item"))
    if finished_qty and frappe.get_meta("Stock Entry").has_field("fg_completed_qty"):
        se.fg_completed_qty = finished_qty
    se.flags.ignore_validate_update_after_submit = True
    se.insert(ignore_permissions=True)
    # back-link stamped after insert (custom fields exist on Stock Entry)
    if from_doctype == "Fish Processing":
        se.mb_fish_processing = from_docname
    elif from_doctype == "Fish Waste Record":
        se.mb_fish_waste_record = from_docname
    elif from_doctype == "Fish Stock Transfer":
        se.mb_fish_transfer = from_docname
    se.save(ignore_permissions=True)
    if submit:
        se.submit()
    return se


def _default_entry_type(purpose):
    return {
        "Material Receipt": "Material Receipt",
        "Material Transfer": "Material Transfer",
        "Material Issue": "Material Issue",
        "Material Consumption for Manufacture": "Material Consumption for Manufacture",
        "Manufacture": "Manufacture",
        "Repack": "Repack",
    }.get(purpose, purpose)


# ---------------------------------------------------------------- reservations
def create_sales_order_reservation(sales_order, branch, warehouse, lines):
    """Create standard Stock Reservation Entries for a sales order (KG).

    Returns list of SRE names. Falls back to custom reservation ledger when SRE
    is unavailable in the running ERPNext build.
    """
    sre_names = []
    try:
        from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
            create_stock_reservation_entries_for_so_items as _so_sre,
        )
        for line in lines:
            try:
                _so_sre(
                    sales_order.name,
                    items=[{
                        "sales_order_item": line.so_item_row,
                        "warehouse": warehouse,
                        "qty": flt(line.kg),
                    }],
                    from_voucher_type="Sales Order",
                    voucher_no=sales_order.name,
                )
            except TypeError:
                _so_sre(sales_order.name)
        for d in frappe.db.get_all(
            "Stock Reservation Entry",
            {"voucher_no": sales_order.name, "docstatus": 1},
            pluck="name",
        ):
            sre_names.append(d)
    except Exception:
        frappe.log_error(title="SRE create failed, fallback to custom",
                         message=frappe.get_traceback())
        _create_custom_reservation(sales_order, branch, warehouse, lines)
    return sre_names


def _create_custom_reservation(sales_order, branch, warehouse, lines):
    from manase_butcher.doctype_compat import append_custom_reservation
    for line in lines:
        append_custom_reservation(
            sales_order=sales_order.name, customer=sales_order.customer,
            branch=branch, warehouse=warehouse, item=line.item, kg=line.kg,
            expires_at=line.expires_at, customer_order=line.customer_order)


def _sre_names_for_order(order, customer_order_name=None):
    names = []
    if frappe.db.exists("DocType", "Stock Reservation Entry"):
        if customer_order_name and frappe.db.has_column(
                "Stock Reservation Entry", "mb_customer_order"):
            names += frappe.db.get_all(
                "Stock Reservation Entry",
                {"mb_customer_order": customer_order_name, "docstatus": ["<", 2]},
                pluck="name")
        if order and order.sales_order:
            # field name varies across ERPNext builds: voucher_type / from_voucher_type
            for vf in ("voucher_type", "from_voucher_type"):
                if frappe.db.has_column("Stock Reservation Entry", vf):
                    names += frappe.db.get_all(
                        "Stock Reservation Entry",
                        {vf: "Sales Order", "voucher_no": order.sales_order,
                         "docstatus": ["<", 2]}, pluck="name")
    return list(dict.fromkeys(names))


def release_order_reservations(customer_order_name):
    """Cancel SREs / release custom reservations for a Customer Order."""
    order = frappe.get_doc("Customer Order", customer_order_name)
    for sre in _sre_names_for_order(order, customer_order_name):
        doc = frappe.get_doc("Stock Reservation Entry", sre)
        if doc.docstatus == 1:
            doc.flags.ignore_permissions = True
            doc.cancel()
    for r in frappe.db.get_all("Stock Reservation",
                               {"customer_order": customer_order_name, "status": "Reserved",
                                "docstatus": ["<", 2]}, pluck="name"):
        rd = frappe.get_doc("Stock Reservation", r)
        rd.status = "Released"
        if rd.docstatus == 1:
            rd.flags.ignore_permissions = True
            rd.cancel()
        else:
            rd.save(ignore_permissions=True)
    _decrement_custom_reserved_bin(order)


def _decrement_custom_reserved_bin(order):
    existing = frappe.db.get_all(
        "Stock Reservation",
        {"customer": order.customer, "customer_order": order.name, "status": "Consumed"},
        fields=["warehouse", "item", "reserved_kg"])
    # Bin custom reserved kg is reconciled by a periodic job; immediate adjustment:
    for r in existing:
        try:
            current = frappe.db.get_value("Bin",
                {"item_code": r.item, "warehouse": r.warehouse},
                ["name", "mb_custom_reserved_kg"], as_dict=True)
            if current:
                frappe.db.set_value("Bin", current.name, "mb_custom_reserved_kg",
                                    max(0, flt(current.mb_custom_reserved_kg) - flt(r.reserved_kg)))
        except Exception:
            frappe.log_error(title="Bin reserved release failed", message=frappe.get_traceback())


# ---------------------------------------------------------------- ledger queries
def opening_kg(item_code, warehouses, before_datetime):
    """KG on hand for an item across warehouses just before a datetime."""
    if not warehouses:
        return 0
    row = frappe.db.sql(
        """
        SELECT COALESCE(SUM(qty_after_transaction), 0)
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
          AND warehouse IN %s
          AND posting_datetime < %s
          AND is_cancelled = 0
          AND name = (
              SELECT name FROM `tabStock Ledger Entry` s2
              WHERE s2.item_code = `tabStock Ledger Entry`.item_code
                AND s2.warehouse = `tabStock Ledger Entry`.warehouse
                AND s2.posting_datetime < %s
              ORDER BY s2.posting_datetime DESC, s2.creation DESC LIMIT 1)
        """, (item_code, tuple(warehouses), before_datetime, before_datetime))
    return flt(row[0][0]) if row else 0


def movement_kg(item_code, warehouses, start, end):
    """Return a dict of KG movement buckets reconstructed from the Stock Ledger."""
    buckets = {k: 0.0 for k in (
        "purchases", "processing_in", "processing_out", "waste",
        "transfers_in", "transfers_out", "sales", "sales_returns",
        "adjustments", "material_receipt_other", "other")}
    if not warehouses:
        return buckets
    rows = frappe.db.sql(
        """
        SELECT sle.actual_qty, sle.voucher_type, sle.voucher_no,
               se.purpose, se.mb_stage AS stage,
               si.is_return, se.mb_fish_waste_record AS waste_doc,
               sle.warehouse
        FROM `tabStock Ledger Entry` sle
        LEFT JOIN `tabStock Entry` se ON se.name = sle.voucher_no
        LEFT JOIN `tabSales Invoice` si ON si.name = sle.voucher_no
        WHERE sle.item_code = %s AND sle.warehouse IN %s
          AND sle.posting_datetime BETWEEN %s AND %s
          AND sle.is_cancelled = 0
        """, (item_code, tuple(warehouses), start, end), as_dict=True)
    for r in rows:
        q = flt(r.actual_qty)
        if r.voucher_type == "Purchase Receipt":
            buckets["purchases"] += q
        elif r.voucher_type == "Sales Invoice":
            if cint(r.is_return):
                buckets["sales_returns"] += q
            else:
                buckets["sales"] += q
        elif r.voucher_type == "Stock Reconciliation":
            buckets["adjustments"] += q
        elif r.voucher_type == "Stock Entry":
            if r.waste_doc:
                buckets["waste"] += q
            elif r.purpose == "Manufacture":
                if q > 0:
                    buckets["processing_out"] += q
                else:
                    buckets["processing_in"] += q
            elif r.purpose == "Material Issue":
                buckets["waste"] += q
            elif r.purpose in ("Material Transfer", "Send to Warehouse", "Receive at Warehouse"):
                if q > 0:
                    buckets["transfers_in"] += q
                else:
                    buckets["transfers_out"] += q
            elif r.purpose == "Material Receipt":
                buckets["material_receipt_other"] += q
            else:
                buckets["other"] += q
        else:
            buckets["other"] += q
    return buckets
