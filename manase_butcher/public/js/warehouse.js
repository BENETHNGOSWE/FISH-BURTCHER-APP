// Warehouse: link branch automatically when kind = Branch
frappe.ui.form.on("Warehouse", {
	custom_mb_warehouse_kind(frm) {
		if (frm.doc.custom_mb_warehouse_kind !== "Branch") {
			frm.set_value("custom_mb_branch", null);
		}
	},
});
