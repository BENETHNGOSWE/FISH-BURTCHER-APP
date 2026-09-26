frappe.ui.form.on("Daily Branch Closing", {
    refresh(frm) {
        if (frm.is_new() || !frm.doc.branch || !frm.doc.posting_date) return;
        frm.add_custom_button(__("Fetch Transactions"), () => {
            frm.call("fetch_data").then(() => frm.reload_doc());
        }, __("Actions"));
    }
});
