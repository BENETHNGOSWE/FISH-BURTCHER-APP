# -*- coding: utf-8 -*-
"""Immutable audit trail writer (Audit Log).

Audit Log rows can only be created server-side (ignore_permissions). No role has
write/delete access to the doctype, giving a tamper-evident operational trail.
"""
import json
import frappe
from frappe.utils import now_datetime


def _client_ip():
    try:
        return frappe.local.request_ip or (frappe.request.headers.get("X-Forwarded-For", "") if frappe.request else None)
    except Exception:
        return None


def _stringify(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, default=str)[:14000]
    except Exception:
        return str(v)[:14000]


def log_action(reference_doctype=None, reference_name=None, action="Update",
               field_label=None, old_value=None, new_value=None, reason=None,
               branch=None, user=None, commit=False):
    """Insert an Audit Log entry. Safe to call inside submit transactions."""
    try:
        doc = frappe.get_doc({
            "doctype": "Audit Log",
            "posting_datetime": now_datetime(),
            "user": user or frappe.session.user,
            "branch": branch,
            "transaction_doctype": reference_doctype,
            "transaction_name": reference_name,
            "action": action,
            "field_label": field_label,
            "old_value": _stringify(old_value),
            "new_value": _stringify(new_value),
            "reason": reason,
            "ip_address": _client_ip(),
        })
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.insert()
        if commit:
            frappe.db.commit()
        return doc.name
    except Exception:
        frappe.log_error(title="MANASE Audit Log failure", message=frappe.get_traceback())
        return None
