# -*- coding: utf-8 -*-
"""Firebase Cloud Messaging v1 (HTTP) sender.

Requires a service-account JSON in Manase Butcher Settings. When google-auth is
not installed or dry-run is enabled, messages are logged instead of sent.
"""
import json
import time

import frappe
from frappe.utils import now_datetime

from manase_butcher.branch_utils import get_settings

FCM_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
_token_cache = None


def _access_token(settings):
    global _token_cache
    if _token_cache and _token_cache[1] > time.time() + 60:
        return _token_cache[0]
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        import requests  # noqa: F401
    except ImportError:
        return None
    sa = json.loads(settings.fcm_service_account or "{}")
    creds = service_account.Credentials.from_service_account_info(
        sa, scopes=["https://www.googleapis.com/auth/firebase.messaging"])
    creds.refresh(Request())
    _token_cache = (creds.token, time.time() + max(60, int(creds.expiry.timestamp() - time.time())))
    return creds.token


def send_to_tokens(tokens, title, body, data=None, customer=None):
    settings = get_settings()
    results = []
    for token in tokens:
        payload = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "data": {k: str(v) for k, v in (data or {}).items()},
                "android": {"priority": "HIGH"},
            }
        }
        status, response = "Queued", ""
        try:
            if not settings.fcm_enabled or settings.fcm_dry_run or not settings.fcm_project_id:
                status, response = "Sent", "dry-run/logged"
                frappe.logger().info(f"[FCM dry-run] {token} {title}: {body}")
            else:
                access = _access_token(settings)
                if not access:
                    status, response = "Failed", "google-auth not installed"
                else:
                    import requests
                    r = requests.post(FCM_URL.format(project=settings.fcm_project_id),
                                      json=payload, timeout=15,
                                      headers={"Authorization": f"Bearer {access}"})
                    status, response = ("Sent" if r.ok else "Failed"), r.text[:1000]
        except Exception as e:
            status, response = "Failed", str(e)[:1000]
        results.append((token, status, response))
        _log(customer, title, body, status, response, data)
    return results


def _log(customer, title, body, status, response, data):
    try:
        frappe.get_doc({
            "doctype": "Notification Log",
            "to_customer": customer,
            "channel": "FCM",
            "status": status,
            "title": title,
            "message": body,
            "provider_response": (response or "")[:1000],
            "reference_doctype": (data or {}).get("doctype"),
            "reference_name": (data or {}).get("name"),
            "sent_at": now_datetime(),
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(title="FCM log failure", message=frappe.get_traceback())
