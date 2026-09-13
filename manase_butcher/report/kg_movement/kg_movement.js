// Copyright (c) 2026 MANASE BUTCHER
frappe.listview_settings = undefined;
frappe.query_reports["Where Did The KG Go?"] = {
	filters: [
		{fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company")},
		{fieldname: "item_code", label: __("Fish Item"), fieldtype: "Link", options: "Item"},
		{fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse"},
		{fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1)},
		{fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today()},
	],
};
