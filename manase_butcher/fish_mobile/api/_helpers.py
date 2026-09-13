# -*- coding: utf-8 -*-
"""Shared API helpers: auth gating, params, geometry, JSON responses."""
import math
import frappe
from frappe.utils import cint, flt

from manase_butcher.mobile_auth import get_current_customer

PROVIDERS = ("Cash", "M-Pesa", "Tigo Pesa", "Airtel Money", "HaloPesa", "Bank", "Card", "Credit")


def begin():
    """Mark request as mobile API (bypasses desk branch filters; ownership is
    enforced explicitly per endpoint) and return current customer."""
    frappe.local.flags.in_mobile_api = True
    return get_current_customer()


def param(name, default=None):
    return frappe.form_dict.get(name, default)


def json_param(name, default=None):
    import json
    v = param(name, default)
    if isinstance(v, (dict, list)):
        return v
    if v:
        try:
            return json.loads(v)
        except Exception:
            return default
    return default


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(flt(lat1)), math.radians(flt(lat2))
    dp = math.radians(flt(lat2) - flt(lat1))
    dl = math.radians(flt(lon2) - flt(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 2)


def rate_limit(key, limit, window=60):
    cache = frappe.cache()
    n = cache.incr(f"mb-api:{key}")
    if n == 1:
        cache.expire(f"mb-api:{key}", window)
    if n and n > limit:
        frappe.throw("Too many requests, slow down.", exc=frappe.RateLimitExceededError)


def public_customer_payload(name):
    customer, phone, preferred = frappe.db.get_value(
        "Customer", name, ["name", "mobile_no", "custom_mb_preferred_branch"])
    return {
        "name": customer,
        "phone": phone,
        "customer_name": frappe.db.get_value("Customer", name, "customer_name"),
        "preferred_branch": preferred,
    }
