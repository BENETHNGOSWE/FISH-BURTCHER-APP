# -*- coding: utf-8 -*-
"""Phone normalisation, OTP generation/verification and SMS gateway dispatch.

OTPs are stored only as salted SHA-256 hashes; rate limits use Redis counters.
"""
import hashlib
import hmac
import json
import secrets
import time

import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date, cint

from manase_butcher.branch_utils import get_settings


def normalize_phone(phone):
    """Normalize Tanzanian phone numbers to +255XXXXXXXXXX."""
    if not phone:
        frappe.throw(_("Phone number is required"))
    p = "".join(ch for ch in str(phone) if ch.isdigit() or ch == "+")
    digits = p.lstrip("+")
    if digits.startswith("0") and len(digits) == 10:
        digits = "255" + digits[1:]
    if digits.startswith("255") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("7") or digits.startswith("6"):
        if len(digits) == 9:
            return "+255" + digits
    if len(digits) >= 11 and digits.startswith("255"):
        return "+" + digits
    frappe.throw(_("Invalid phone number: {0}").format(phone))


def _secret():
    return frappe.get_site_config().get("retry_otp_secret") or frappe.local.site


def hash_otp(phone, otp):
    return hashlib.sha256(f"{phone}|{otp}|{_secret()}".encode()).hexdigest()


def hash_token(token):
    return hashlib.sha256(f"{token}|{_secret()}".encode()).hexdigest()


# ---------------------------------------------------------------- rate limiting
def rate_limit(key, limit, window_seconds):
    cache = frappe.cache()
    n = cache.incr(key)
    if n == 1:
        cache.expire(key, window_seconds)
    if n and n > limit:
        frappe.throw(_("Too many requests. Please try again later."),
                     exc=frappe.RateLimitExceededError, title=_("Rate limited"))
    return n


def _ip():
    try:
        return frappe.local.request_ip
    except Exception:
        return None


# ---------------------------------------------------------------- OTP lifecycle
def request_otp(phone, purpose="Login", device_id=None):
    settings = get_settings()
    phone = normalize_phone(phone)
    window = 600
    rate_limit(f"otp-req:{phone}", settings.otp_rate_per_window or 3, window)
    rate_limit(f"otp-req-ip:{_ip()}", 20, window)
    length = cint(settings.otp_length) or 6
    otp = "".join(str(secrets.randbelow(10)) for _ in range(length))
    # avoid leading-zero scanner confusion is not necessary; keep all digits valid
    expires = add_to_date(now_datetime(), minutes=cint(settings.otp_validity_minutes) or 5)
    log = frappe.get_doc({
        "doctype": "OTP Log",
        "phone": phone,
        "otp_hash": hash_otp(phone, otp),
        "purpose": purpose,
        "status": "Pending",
        "attempts": 0,
        "generated_at": now_datetime(),
        "expires_at": expires,
        "ip_address": _ip(),
        "device_id": device_id,
    })
    log.flags.ignore_permissions = True
    log.insert(ignore_permissions=True)
    message = f"MANASE BUTCHER: your verification code is {otp}. It expires in " \
              f"{cint(settings.otp_validity_minutes) or 5} minutes. Never share it."
    send_sms(phone, message)
    frappe.db.commit()
    return {"status": "sent", "expires_at": expires.isoformat()}


def verify_otp(phone, otp, device_id=None):
    phone = normalize_phone(phone)
    rate_limit(f"otp-verify:{phone}", 8, 600)
    log_name = frappe.db.get_value(
        "OTP Log",
        {"phone": phone, "status": "Pending", "expires_at": [">", now_datetime()]},
        "name", order_by="creation desc")
    if not log_name:
        frappe.throw(_("OTP expired or not found. Request a new code."),
                     exc=frappe.AuthenticationError)
    log = frappe.get_doc("OTP Log", log_name)
    log.attempts = cint(log.attempts) + 1
    if not hmac.compare_digest(log.otp_hash, hash_otp(phone, str(otp).strip())):
        if log.attempts >= 5:
            log.status = "Cancelled"
        log.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.throw(_("Invalid verification code."), exc=frappe.AuthenticationError)
    log.status = "Verified"
    log.verified_at = now_datetime()
    log.save(ignore_permissions=True)
    frappe.db.commit()
    return phone


# ---------------------------------------------------------------- SMS dispatch
def send_sms(to, message):
    """Dispatch SMS via the configured gateway; log-only fallback for development."""
    settings = get_settings()
    gateway = settings.sms_gateway or "Log (development)"
    to = normalize_phone(to) if not str(to).startswith("+") else to
    try:
        if gateway == "Africa's Talking":
            return _send_africastalking(settings, to, message)
        if gateway == "Beem":
            return _send_beem(settings, to, message)
        if gateway == "Generic HTTP":
            return _send_generic(settings, to, message)
    except Exception:
        frappe.log_error(title="SMS send failed", message=frappe.get_traceback())
        _log_notification(to, message, "SMS", "Failed", frappe.get_traceback())
        return False
    frappe.logger().info(f"[MANASE OTP/SMS] {to}: {message}")
    _log_notification(to, message, "SMS", "Sent", "logged (development)")
    return True


def _post_json(url, payload, headers=None):
    import requests
    return requests.post(url, json=payload, headers=headers or {}, timeout=15)


def _send_africastalking(settings, to, message):
    import requests
    url = settings.sms_api_url or "https://api.africastalking.com/version1/messaging"
    r = requests.post(url, data={"username": settings.sms_api_key,
                                 "to": to, "message": message,
                                 "from": settings.sms_sender_id or None},
                      headers={"apiKey": settings.get_password("sms_api_secret")}, timeout=15)
    _log_notification(to, message, "SMS", "Sent" if r.ok else "Failed", r.text[:1000])
    r.raise_for_status()
    return True


def _send_beem(settings, to, message):
    import requests
    url = settings.sms_api_url or "https://apisms.beem.africa/v1/send"
    import base64
    auth = base64.b64encode(
        f"{settings.sms_api_key}:{settings.get_password('sms_api_secret')}".encode()).decode()
    r = requests.post(url, json=[{"sender_id": settings.sms_sender_id or "MANASE",
                                 "recipient": to, "message": message}],
                      headers={"Authorization": f"Basic {auth}"}, timeout=15)
    _log_notification(to, message, "SMS", "Sent" if r.ok else "Failed", r.text[:1000])
    r.raise_for_status()
    return True


def _send_generic(settings, to, message):
    import requests
    r = requests.post(settings.sms_api_url, json={"to": to, "message": message,
                      "key": settings.get_password("sms_api_secret"),
                      "sender": settings.sms_sender_id}, timeout=15)
    _log_notification(to, message, "SMS", "Sent" if r.ok else "Failed", r.text[:1000])
    r.raise_for_status()
    return True


def _log_notification(phone, message, channel, status, response):
    try:
        frappe.get_doc({
            "doctype": "Notification Log",
            "phone": phone, "channel": channel, "status": status,
            "title": message[:60], "message": message,
            "provider_response": (response or "")[:1000],
        }).insert(ignore_permissions=True)
    except Exception:
        pass
