# -*- coding: utf-8 -*-
"""Authentication: phone + OTP, opaque bearer sessions, refresh/logout."""
import frappe

from manase_butcher.otp import request_otp as _request, verify_otp as _verify
from manase_butcher.mobile_auth import (
    create_session, rotate_session, logout as _logout, register_device)
from ._helpers import param, begin


@frappe.whitelist(allow_guest=True)
def request_otp():
    phone = param("phone")
    device_id = param("device_id")
    result = _request(phone, purpose="Login", device_id=device_id)
    return {"ok": True, "data": result}


@frappe.whitelist(allow_guest=True)
def verify_otp():
    phone = param("phone")
    otp = param("otp")
    device_id = param("device_id")
    fcm_token = param("fcm_token")
    platform = param("platform")
    app_version = param("app_version")
    phone = _verify(phone, otp, device_id)
    session = create_session(phone, device_id=device_id, fcm_token=fcm_token,
                             platform=platform, app_version=app_version)
    from manase_butcher.mobile_auth import find_or_create_customer
    customer, _ = find_or_create_customer(phone)
    return {"ok": True, "data": {"session": session,
                                "customer": _customer_brief(customer)}}


@frappe.whitelist(allow_guest=True)
def refresh():
    frappe.local.flags.in_mobile_api = True
    return {"ok": True, "data": rotate_session()}


@frappe.whitelist(allow_guest=True)
def logout():
    frappe.local.flags.in_mobile_api = True
    return {"ok": True, "data": _logout()}


@frappe.whitelist(allow_guest=False)
def register_push(fcm_token=None, platform=None):
    customer, sess = begin()
    register_device(customer, device_id=sess.device_id, fcm_token=fcm_token or param("fcm_token"),
                    platform=platform or param("platform"))
    return {"ok": True}


def _customer_brief(customer):
    d = frappe.db.get_value("Customer", customer,
                            ["name", "customer_name", "mobile_no",
                             "mb_preferred_branch"], as_dict=True)
    return {
        "name": d.name,
        "customer_name": d.customer_name,
        "phone": d.mobile_no,
        "preferred_branch": d.mb_preferred_branch,
    }
