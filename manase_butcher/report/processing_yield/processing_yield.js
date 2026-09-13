// Copyright (c) 2026 MANASE BUTCHER
frappe.listview_settings = undefined;
frappe.query_reports["Processing Yield"] = {
	filters: [
		{fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1)},
		{fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today()},
		{fieldname: "item_code", label: __("Fish Item"), fieldtype: "Link", options: "Item"},
		{fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier"},
		{fieldname: "employee", label: __("Processor"), fieldtype: "Link", options: "Employee"},
	],
};
