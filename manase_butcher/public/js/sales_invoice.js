// Sales Invoice: derive branch + KG from warehouse and fish items.
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (!frm.doc.mb_branch) {
			window.manase_butcher.sync_branch_from_warehouse(frm, "set_warehouse");
		}
	},
	set_warehouse(frm) {
		window.manase_butcher.sync_branch_from_warehouse(frm, "set_warehouse");
	},
});
