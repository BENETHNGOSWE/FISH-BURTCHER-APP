# -*- coding: utf-8 -*-
"""Customer profile, addresses (standard Address), own orders/payments."""
import frappe
from frappe.utils import flt

from ._helpers import begin, param
from manase_butcher.otp import normalize_phone


@frappe.whitelist()
def profile():
    customer, sess = begin()
    d = frappe.db.get_value("Customer", customer,
                            ["name", "customer_name", "mobile_no", "email_id",
                             "custom_mb_preferred_branch", "territory",
                             "total_unpaid"], as_dict=True)
    return {"ok": True, "data": {
        "name": d.name, "customer_name": d.customer_name, "phone": d.mobile_no,
        "email": d.email_id, "preferred_branch": d.custom_mb_preferred_branch,
        "outstanding": flt(d.total_unpaid),
        "verified": bool(frappe.db.get_value("Customer", customer,
                                              "custom_mb_phone_verified")),
    }}


@frappe.whitelist()
def update_profile():
    customer, sess = begin()
    name = param("customer_name")
    email = param("email")
    values = {}
    if name:
        values["customer_name"] = name
    if email:
        values["email_id"] = email
    if values:
        frappe.db.set_value("Customer", customer, values, update_modified=False)
    return {"ok": True}


@frappe.whitelist()
def addresses():
    customer, sess = begin()
    names = frappe.db.get_all("Dynamic Link",
                              filters={"link_doctype": "Customer", "link_docname": customer,
                                       "parenttype": "Address"},
                              pluck="parent")
    rows = []
    for n in names:
        a = frappe.db.get_value("Address", n,
                                ["name", "address_title", "address_line1", "address_line2",
                                 "city", "state", "country", "phone",
                                 "latitude", "longitude"], as_dict=True)
        if a:
            rows.append(a)
    return {"ok": True, "data": rows}


@frappe.whitelist()
def save_address():
    customer, sess = begin()
    name = param("name")
    if name and not frappe.db.exists("Dynamic Link",
                                    {"parenttype": "Address", "parent": name,
                                     "link_doctype": "Customer", "link_docname": customer}):
        frappe.throw("Address not found", frappe.PermissionError)
    doc = frappe.get_doc("Address", name) if name else frappe.new_doc("Address")
    doc.address_title = param("label") or doc.address_title or "Home"
    doc.address_type = param("label") or doc.address_type
    doc.address_line1 = param("address_line1") or doc.address_line1
    doc.address_line2 = param("details") or doc.address_line2
    doc.city = param("city") or doc.city
    doc.phone = param("phone") or (doc.phone if name else frappe.db.get_value(
        "Customer", customer, "mobile_no"))
    if param("latitude"):
        doc.latitude = float(param("latitude"))
        doc.longitude = float(param("longitude"))
    doc.country = doc.country or "Tanzania"
    linked = any(l.link_doctype == "Customer" and l.link_docname == customer
                 for l in doc.links)
    if not linked:
        doc.append("links", {"link_doctype": "Customer", "link_docname": customer})
    doc.flags.ignore_permissions = True
    doc.save()
    return {"ok": True, "data": {"address": doc.name}}


@frappe.whitelist()
def delete_address():
    customer, sess = begin()
    name = param("name")
    if not frappe.db.exists("Dynamic Link",
                           {"parenttype": "Address", "parent": name,
                            "link_doctype": "Customer", "link_docname": customer}):
        frappe.throw("Address not found", frappe.PermissionError)
    frappe.delete_doc("Address", name, ignore_permissions=True)
    return {"ok": True}


@frappe.whitelist()
def payments():
    customer, sess = begin()
    rows = frappe.db.get_all("Payment Entry",
                             filters={"party_type": "Customer", "party": customer,
                                      "docstatus": 1},
                             fields=["name", "posting_date", "mode_of_payment",
                                     "custom_mb_mobile_provider as provider",
                                     "paid_amount",
                                     "custom_mb_mobile_reference as reference"],
                             order_by="posting_date desc", limit=100)
    invoices = frappe.db.get_all("Sales Invoice",
                                 filters={"customer": customer, "docstatus": 1},
                                 fields=["name", "posting_date", "grand_total",
                                         "outstanding_amount"],
                                 order_by="posting_date desc", limit=100)
    return {"ok": True, "data": {"payments": rows, "invoices": invoices}}


@frappe.whitelist()
def balance():
    customer, sess = begin()
    return {"ok": True, "data": {
        "outstanding": flt(frappe.db.get_value("Customer", customer, "total_unpaid"))}}
