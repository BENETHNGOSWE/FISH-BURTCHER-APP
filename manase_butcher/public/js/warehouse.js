// Warehouse: link branch automatically when kind = Branch
frappe.ui.form.on("Warehouse", {
	mb_warehouse_kind(frm) {
		if (frm.doc.mb_warehouse_kind !== "Branch") {
			frm.set_value("mb_branch", null);
		}
	},
});
