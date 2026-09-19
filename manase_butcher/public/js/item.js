// Item: fish defaults (stock UOM Kg, weight-based inventory).
frappe.ui.form.on("Item", {
	refresh(frm) {
		if (frm.doc.mb_is_fish) {
			frm.set_df_property("stock_uom", "read_only", 1);
		}
	},
	mb_is_fish(frm) {
		if (frm.doc.mb_is_fish) {
			if (!frm.doc.stock_uom) frm.set_value("stock_uom", "Kg");
			frm.set_value("is_stock_item", 1);
			frm.set_value("mb_freshness", frm.doc.mb_freshness || "Fresh");
		}
	},
	mb_species(frm) {
		if (frm.doc.mb_species) {
			frappe.db.get_value("Fish Species", frm.doc.mb_species, "image").then((r) => {
				if (r && r.message && r.message.image && !frm.doc.image)
					frm.set_value("image", r.message.image);
			});
		}
	},
});
