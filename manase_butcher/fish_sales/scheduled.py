# -*- coding: utf-8 -*-
"""Sales/finance scheduled jobs: debt reminders, closing reminders."""
import frappe
from frappe.utils import flt, add_days, today


def debt_reminders():
    """SMS customers with overdue balances (daily). Uses standard AR data."""
    try:
        rows = frappe.db.sql(
            """SELECT si.customer, c.customer_name, c.mobile_no,
                      SUM(si.outstanding_amount) AS balance,
                      MIN(DATEDIFF(CURDATE(), si.due_date)) AS days_overdue
               FROM `tabSales Invoice` si
               JOIN tabCustomer c ON c.name = si.customer
               WHERE si.docstatus=1 AND si.outstanding_amount > 0
                 AND si.due_date IS NOT NULL AND si.due_date < CURDATE()
                 AND c.mobile_no IS NOT NULL AND c.mobile_no != ''
               GROUP BY si.customer
               HAVING days_overdue >= COALESCE((SELECT value FROM tabSingles
                  WHERE doctype='Manase Butcher Settings' AND field='reminder_after_days'), 1)""",
            as_dict=True)
        for r in rows:
            msg = (f"MANASE BUTCHER: Dear {r.customer_name}, your outstanding balance is "
                   f"{flt(r.balance):,.0f} TZS overdue by {r.days_overdue} days. "
                   f"Please pay via M-Pesa/Tigo/Airtel/Halo or visit your branch. Asante.")
            try:
                from manase_butcher.otp import send_sms
                send_sms(r.mobile_no, msg)
            except Exception:
                frappe.log_error(title="Debt reminder failed", message=frappe.get_traceback())
    except Exception:
        frappe.log_error(title="debt_reminders failed", message=frappe.get_traceback())


def daily_closing_reminder():
    """Ping branches without a closing for today at end of day."""
    branches = frappe.db.get_all("Branch", filters={"is_active": 1}, pluck="name")
    manager_msgs = []
    for branch in branches:
        exists = frappe.db.exists("Daily Branch Closing",
                                  {"branch": branch, "posting_date": today()})
        if exists:
            continue
        manager = frappe.db.get_value("Branch", branch, "manager")
        if not manager:
            continue
        try:
            frappe.publish_realtime(
                event="msgprint",
                message=f"Reminder: daily closing for {branch} is not done yet.",
                user=manager)
            manager_msgs.append((branch, manager))
        except Exception:
            pass
    return manager_msgs
