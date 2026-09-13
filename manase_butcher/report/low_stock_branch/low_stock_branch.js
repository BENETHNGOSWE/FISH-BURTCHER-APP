// Copyright (c) 2026 MANASE BUTCHER
frappe.listview_settings = undefined;
frappe.query_reports["Low Stock by Branch"] = {
	filters: [
		{fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch"},
	],
};
