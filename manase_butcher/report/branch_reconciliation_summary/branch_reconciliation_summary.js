// Copyright (c) 2026 MANASE BUTCHER
frappe.listview_settings = undefined;
frappe.query_reports["Branch Reconciliation Summary"] = {
	filters: [
		{fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch"},
		{fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1)},
		{fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today()},
	],
};
