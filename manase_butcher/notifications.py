# -*- coding: utf-8 -*-
"""Customer notification dispatcher: FCM push with SMS fallback, plus desk alerts."""
import frappe

from manase_butcher import fcm
from manase_butcher.otp import send_sms


def customer_tokens(customer):
    rows = frappe.db.get_all("Mobile Device",
                             filters={"customer": customer},
                             fields=["fcm_token"])
    return [r.fcm_token for r in rows if r.fcm_token]


def notify_customer(customer, title, message, data=None, sms_fallback=False):
    tokens = customer_tokens(customer)
    results = []
    if tokens:
        results = fcm.send_to_tokens(tokens, title, message, data=data, customer=customer)
    elif sms_fallback:
        phone = frappe.db.get_value("Customer", customer, "mobile_no")
        if phone:
            send_sms(phone, f"{title}. {message}")
    return results


def notify_branch_users(branch, message, doctype=None, docname=None):
    """Desk + FCM notification for staff users attached to a branch."""
    manager = frappe.db.get_value("Branch", branch, "manager")
    users = []
    # branch manager + users whose User Permission points at this branch
    if manager:
        users.append(manager)
    users += frappe.db.get_all("User Permission",
                               filters={"allow": "Branch", "for_value": branch},
                               pluck="user")
    for user in sorted(set(users)):
        if not user or user == "Administrator":
            continue
        try:
            frappe.publish_realtime(event="msgprint", message=message, user=user)
            doc = frappe.new_doc("Notification Log")
            doc.from_user = "Administrator"
            doc.for_user = user
            doc.type = "Mention"
            doc.document_type = doctype or "Customer Order"
            doc.document_name = docname
            doc.subject = message
            doc.flags.ignore_permissions = True
            doc.insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title="branch notify failure", message=frappe.get_traceback())
