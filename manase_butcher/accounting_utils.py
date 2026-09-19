# -*- coding: utf-8 -*-
"""Accounting helpers: Mode of Payment resolution, Payment Entry and Journal Entry."""
import frappe
from frappe import _
from frappe.utils import flt, nowdate


def get_payment_account(mode_of_payment, company):
    """Default account configured for a Mode of Payment in a company."""
    if not mode_of_payment:
        return None
    rows = frappe.get_all(
        "Mode of Payment Account",
        filters={"parent": mode_of_payment, "company": company},
        fields=["default_account"],
    )
    return rows[0].default_account if rows else None


def make_payment_entry(company, payment_type, paid_amount, party_type=None, party=None,
                       mode_of_payment=None, payment_account=None,
                       reference_doctype=None, reference_name=None,
                       posting_date=None, cost_center=None, branch=None,
                       mobile_provider=None, mobile_reference=None,
                       remarks=None, submit=True):
    """Create a balanced Payment Entry.

    payment_type 'Receive' -> customer receipt; 'Pay' -> supplier/expense outflow.
    """
    paid_amount = flt(paid_amount)
    if paid_amount <= 0:
        return None
    pe = frappe.new_doc("Payment Entry")
    pe.company = company
    pe.payment_type = payment_type
    pe.posting_date = posting_date or nowdate()
    pe.mode_of_payment = mode_of_payment
    if party_type and party:
        pe.party_type = party_type
        pe.party = party
    if payment_type == "Receive":
        pe.paid_to = payment_account or get_payment_account(mode_of_payment, company)
        pe.paid_from = pe.paid_from or frappe.db.get_value(
            "Company", company, "default_receivable_account")
    else:
        pe.paid_from = payment_account or get_payment_account(mode_of_payment, company)
        pe.paid_to = pe.paid_to or frappe.db.get_value(
            "Company", company, "default_payable_account")
    pe.paid_amount = paid_amount
    pe.received_amount = paid_amount
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    pe.remarks = remarks or _("MANASE BUTCHER payment")
    if reference_doctype and reference_name:
        pe.append("references", {
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "allocated_amount": paid_amount,
        })
    pe.flags.ignore_permissions = True
    pe.insert()
    if branch:
        pe.mb_branch = branch
    if mobile_provider:
        pe.mb_mobile_provider = mobile_provider
    if mobile_reference:
        pe.mb_mobile_reference = mobile_reference
    pe.save(ignore_permissions=True)
    if submit:
        pe.submit()
    return pe


def make_journal_entry(company, accounts, posting_date=None, user_remark=None,
                       branch=None, submit=True, chequeno=None):
    """accounts: list of dicts: account, debit, credit, party_type, party, cost_center."""
    je = frappe.new_doc("Journal Entry")
    je.company = company
    je.posting_date = posting_date or nowdate()
    je.user_remark = user_remark or "MANASE BUTCHER"
    if chequeno:
        je.cheque_no = chequeno
        je.cheque_date = je.posting_date
    for a in accounts:
        je.append("accounts", {
            "account": a["account"],
            "debit_in_account_currency": flt(a.get("debit")),
            "credit_in_account_currency": flt(a.get("credit")),
            "party_type": a.get("party_type"),
            "party": a.get("party"),
            "cost_center": a.get("cost_center"),
            "user_remark": a.get("remark"),
            "account_currency": a.get("currency"),
        })
    je.flags.ignore_permissions = True
    je.insert()
    if branch:
        je.mb_branch = branch
    je.save(ignore_permissions=True)
    if submit:
        je.submit()
    return je


def get_outstanding(customer):
    return flt(frappe.db.get_value("Customer", customer, "total_unpaid"))
