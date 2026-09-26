frappe.ui.form.on("Branch Stock Reconciliation", {
    refresh(frm) {
        if (frm.doc.docstatus === 1 || !frm.doc.branch || !frm.doc.warehouse) return;
        frm.add_custom_button(__("Fetch Expected Stock"), () => {
            frm.call("fetch_expected").then(() => frm.reload_doc());
        }, __("Actions"));
    }
});
