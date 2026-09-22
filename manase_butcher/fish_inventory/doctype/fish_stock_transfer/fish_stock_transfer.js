frappe.ui.form.on("Fish Stock Transfer", {
    refresh(frm) {
        frm.events.recalculate_totals(frm);

        if (frm.doc.docstatus !== 1) return;

        if (frm.doc.status === "Submitted") {
            frm.add_custom_button(__("Approve"), () => {
                frm.call("approve").then(() => frm.reload_doc());
            }, __("Actions"));
        }

        if (frm.doc.status === "Approved") {
            frm.add_custom_button(__("Dispatch"), () => {
                frm.call("dispatch").then(() => frm.reload_doc());
            }, __("Actions"));
        }

        if (frm.doc.status === "Dispatched") {
            frm.add_custom_button(__("Receive"), () => {
                const missing_reason = (frm.doc.items || []).some(row => {
                    const difference = flt(row.sent_kg) - flt(row.received_kg);
                    return difference > 0.0005 && !String(row.variance_reason || "").trim();
                });
                if (missing_reason) {
                    frappe.throw(__("Enter a variance reason for every short-received line before receiving."));
                }
                frm.save().then(() => frm.call("receive")).then(() => frm.reload_doc());
            }, __("Actions"));
        }
    },

    validate(frm) {
        frm.events.recalculate_totals(frm);
    },

    recalculate_totals(frm) {
        let sent = 0;
        let received = 0;
        let variance = 0;
        (frm.doc.items || []).forEach(row => {
            const row_variance = flt(row.received_kg) - flt(row.sent_kg);
            frappe.model.set_value(row.doctype, row.name, "variance_kg", row_variance);
            sent += flt(row.sent_kg);
            received += flt(row.received_kg);
            variance += row_variance;
        });
        frm.set_value("total_sent_kg", sent);
        frm.set_value("total_received_kg", received);
        frm.set_value("total_variance_kg", variance);
    }
});

frappe.ui.form.on("Fish Transfer Item", {
    sent_kg(frm) {
        frm.events.recalculate_totals(frm);
    },
    received_kg(frm) {
        frm.events.recalculate_totals(frm);
    }
});
