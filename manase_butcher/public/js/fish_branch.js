// Shared desk helpers for MANASE BUTCHER
window.manase_butcher = window.manase_butcher || {};

// Keep the branch link in sync with the selected warehouse on stock documents.
window.manase_butcher.sync_branch_from_warehouse = function (frm, warehouse_field) {
	if (!frm.fields_dict["mb_branch"]) return;
	const wh = frm.doc[warehouse_field || "set_warehouse"] ||
		(frm.doc.items && frm.doc.items.length ? frm.doc.items[0].warehouse : null);
	if (!wh) return;
	frappe.db.get_value("Warehouse", wh, "mb_branch").then((r) => {
		if (r && r.message && r.message.mb_branch &&
			frm.doc.mb_branch !== r.message.mb_branch) {
			frm.set_value("mb_branch", r.message.mb_branch);
		}
	});
};
