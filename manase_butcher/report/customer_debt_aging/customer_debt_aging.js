// Copyright (c) 2026 MANASE BUTCHER
frappe.listview_settings = undefined;
frappe.query_reports["Customer Debt Aging"] = {
	filters: [
		{fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer"},
		{fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch"},
	],
};
