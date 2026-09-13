# -*- coding: utf-8 -*-
"""Scheduled mobile/order jobs: release stale unconfirmed reservations."""
import frappe
from frappe.utils import now_datetime, get_datetime, cint


def release_expired_reservations():
    """Auto-reject/cancel Pending mobile orders past the validity window."""
    settings = frappe.get_single("Manase Butcher Settings")
    minutes = cint(settings.order_validity_minutes) or 20
    cutoff = frappe.utils.add_to_date(now_datetime(), minutes=-minutes)
    orders = frappe.db.get_all(
        "Customer Order",
        filters={"status": "Pending", "docstatus": ["<", 2], "creation": ["<", cutoff]},
        pluck="name")
    for name in orders:
        try:
            doc = frappe.get_doc("Customer Order", name)
            frappe.local.flags.in_mobile_api = True
            doc.transition("Cancelled",
                           reason=f"Auto-cancelled: not confirmed within {minutes} minutes")
        except Exception:
            frappe.log_error(title="Auto release failed", message=frappe.get_traceback())
    # expire custom reservations past expiry
    for name in frappe.db.get_all("Stock Reservation",
                                  filters={"status": "Reserved",
                                           "expires_at": ["<", now_datetime()]},
                                  pluck="name"):
        try:
            from manase_butcher.doctype_compat import release_custom
            release_custom(name)
        except Exception:
            frappe.log_error(title="Reservation expiry failed", message=frappe.get_traceback())
