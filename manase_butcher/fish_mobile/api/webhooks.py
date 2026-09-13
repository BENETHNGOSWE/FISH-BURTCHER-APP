# -*- coding: utf-8 -*-
"""Provider webhooks (mobile money). Authenticated by per-provider secret/HMAC;
customers never call these directly.
"""
import hashlib
import hmac
import json

import frappe
from frappe.utils import flt


def _check_signature(raw_body, signature, secret):
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body or b"", hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.replace("sha256=", ""))


def _cfg(*keys):
    conf = frappe.conf
    for k in keys:
        if conf.get(k):
            return conf.get(k)
    return None


@frappe.whitelist(allow_guest=True)
def mobile_payment_callback(provider=None, reference=None, amount=None,
                             order=None, phone=None, status="CONFIRMED", **kwargs):
    """Generic mobile-money confirmation endpoint.

    Authenticate with header ``X-MB-Signature`` (HMAC SHA256 of raw body using
    site config key ``mb_webhook_secret``) or provider-specific keys.
    """
    request = frappe.request
    raw = b""
    signature = None
    if request:
        raw = request.get_data() or b""
        signature = request.headers.get("X-MB-Signature")
    secret = _cfg("mb_webhook_secret", f"{(provider or '').lower().replace(' ', '_')}_webhook_secret")
    # fallback header key allow-list for tests/staging
    header_key = request.headers.get("X-MB-Key") if request else None
    if not (_check_signature(raw, signature, secret) or (secret and header_key == secret)):
        frappe.log_error(title="Payment callback rejected",
                         message=f"provider={provider} reference={reference}")
        frappe.throw("Invalid signature", frappe.AuthenticationError)

    payload = {}
    try:
        payload = json.loads(raw.decode()) if raw else {}
    except Exception:
        payload = {}
    provider = provider or payload.get("provider")
    reference = reference or payload.get("reference") or payload.get("transaction_id")
    amount = amount or payload.get("amount")
    order = order or payload.get("order") or payload.get("account")
    status = (status or payload.get("status") or "CONFIRMED").upper()

    if not reference or not amount:
        frappe.throw("reference and amount are required")
    # replay protection
    if frappe.db.exists("Payment Entry",
                        {"custom_mb_mobile_reference": reference, "docstatus": ["!=", 2]}):
        return {"ok": True, "data": {"duplicate": True, "reference": reference}}

    # locate order by explicit id or account-reference mapping
    order_name = order if order and frappe.db.exists("Customer Order", order) else None
    if not order_name and phone:
        from manase_butcher.otp import normalize_phone
        norm = normalize_phone(phone)
        order_name = frappe.db.get_value(
            "Customer Order",
            [["phone", "=", norm],
             ["status", "in", ("Pending", "Confirmed", "Preparing", "Ready")]],
            "name", order_by="creation desc")
    if not order_name:
        frappe.log_error(title="Payment callback without order",
                         message=f"{provider} {reference} {amount}")
        frappe.throw("No matching order")

    if status in ("CONFIRMED", "SUCCESS", "COMPLETED", "PAID"):
        from manase_butcher.fish_mobile.api.orders import confirm_payment
        confirm_payment(order_name, provider, reference, flt(amount), create_pe=True)
    return {"ok": True, "data": {"order": order_name, "reference": reference, "status": status}}
