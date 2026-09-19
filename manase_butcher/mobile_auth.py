# -*- coding: utf-8 -*-
"""Opaque bearer-token session management for the customer mobile API.

Tokens are shown to the customer exactly once; only the SHA-256 hash is stored.
Customers are ERPNext Customer records (never Frappe users / Desk).
"""
import secrets

import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date, get_datetime

from manase_butcher.otp import hash_token, normalize_phone

SESSION_DAYS = 30
SLIDING_REFRESH_DAYS = 7


def find_or_create_customer(phone):
    phone = normalize_phone(phone)
    name = frappe.db.get_value("Customer", {"mobile_no": phone}, "name")
    if name:
        return name, False
    existing = frappe.db.get_value("Customer", {"customer_name": phone}, "name")
    if existing:
        return existing, False
    doc = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": f"Mobile Customer {phone[-9:]}",
        "customer_type": "Individual",
        "customer_group": frappe.db.get_single_value("Selling Settings",
                                                     "customer_group") or "All Customer Groups",
        "territory": frappe.db.get_single_value("Selling Settings", "territory") or "All Territories",
        "mobile_no": phone,
        "mb_phone_verified": 1,
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name, True


def register_device(customer, device_id=None, fcm_token=None, platform=None, app_version=None):
    if not device_id:
        return
    name = frappe.db.get_value("Mobile Device",
                               {"customer": customer, "device_id": device_id}, "name")
    if name:
        doc = frappe.get_doc("Mobile Device", name)
    else:
        doc = frappe.new_doc("Mobile Device")
        doc.customer = customer
        doc.device_id = device_id
    doc.platform = platform
    doc.fcm_token = fcm_token
    doc.app_version = app_version
    doc.last_active = now_datetime()
    doc.flags.ignore_permissions = True
    doc.save()


def create_session(phone, device_id=None, fcm_token=None, platform=None, app_version=None):
    customer, _created = find_or_create_customer(phone)
    register_device(customer, device_id, fcm_token, platform, app_version)
    token = secrets.token_urlsafe(48)
    now = now_datetime()
    doc = frappe.get_doc({
        "doctype": "Mobile Session",
        "customer": customer,
        "phone": normalize_phone(phone),
        "token_hash": hash_token(token),
        "device_id": device_id,
        "platform": platform,
        "fcm_token": fcm_token,
        "issued_at": now,
        "expires_at": add_to_date(now, days=SESSION_DAYS),
        "last_seen": now,
    })
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {
        "token": token,
        "customer": customer,
        "expires_at": doc.expires_at.isoformat(),
    }


def get_bearer_token():
    req = frappe.request
    if not req:
        return None
    auth = req.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return req.headers.get("X-MB-Token")


def get_current_customer(required=True):
    """Validate the bearer token and return (customer_name, session_doc)."""
    token = get_bearer_token()
    if not token:
        if required:
            frappe.throw(_("Authentication required"), exc=frappe.AuthenticationError)
        return None, None
    h = hash_token(token)
    name = frappe.db.get_value("Mobile Session",
                               {"token_hash": h, "revoked": 0}, "name", order_by="creation desc")
    if not name:
        frappe.throw(_("Invalid session"), exc=frappe.AuthenticationError)
    sess = frappe.get_doc("Mobile Session", name)
    if get_datetime(sess.expires_at) < now_datetime():
        frappe.throw(_("Session expired"), exc=frappe.AuthenticationError)
    sess.db_set("last_seen", now_datetime(), update_modified=False)
    frappe.local.flags.mobile_customer = sess.customer
    return sess.customer, sess


def rotate_session(old_token_header=True):
    customer, sess = get_current_customer()
    sess.db_set("revoked", 1, update_modified=False)
    token = secrets.token_urlsafe(48)
    now = now_datetime()
    new = frappe.get_doc({
        "doctype": "Mobile Session",
        "customer": customer, "phone": sess.phone,
        "token_hash": hash_token(token), "device_id": sess.device_id,
        "platform": sess.platform, "fcm_token": sess.fcm_token,
        "issued_at": now, "expires_at": add_to_date(now, days=SESSION_DAYS),
        "last_seen": now,
    })
    new.flags.ignore_permissions = True
    new.insert(ignore_permissions=True)
    return {"token": token, "customer": customer,
            "expires_at": new.expires_at.isoformat()}


def logout():
    token = get_bearer_token()
    if token:
        name = frappe.db.get_value("Mobile Session",
                                   {"token_hash": hash_token(token)}, "name")
        if name:
            frappe.db.set_value("Mobile Session", name, "revoked", 1)
    return {"status": "logged_out"}


def assert_customer_owns(doc_customer):
    customer, _ = get_current_customer()
    if doc_customer != customer:
        frappe.throw(_("Resource not found"), exc=frappe.PermissionError)
    return customer
