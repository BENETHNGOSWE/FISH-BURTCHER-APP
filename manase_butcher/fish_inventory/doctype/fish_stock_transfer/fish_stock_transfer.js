frappe.ui.form.on("Fish Stock Transfer", {
    refresh(frm) {
        frm.events.recalculate_totals(frm);
        frm.events.show_transfer_progress(frm);

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
                const receive_call = () => frm.call("receive").then(() => frm.reload_doc());
                if (frm.is_dirty()) {
                    frm.save().then(receive_call);
                } else {
                    receive_call();
                }
            }, __("Actions"));
        }
    },

    validate(frm) {
        frm.events.recalculate_totals(frm);
    },

    show_transfer_progress(frm) {
        const labels = ["Submitted", "Approved", "Dispatched", "Completed"];
        const current = frm.doc.status === "Received" ? "Completed" : (frm.doc.status || "Draft");
        const current_index = Math.max(labels.indexOf(current), 0);
        const colors = {
            Submitted: "#22c55e",
            Approved: "#f59e0b",
            Dispatched: "#3b82f6",
            Completed: "#16a34a"
        };
        const steps = labels.map((label, index) => {
            const active = index <= current_index;
            const color = active ? colors[label] : "#d1d5db";
            return `<div style="flex:1; text-align:center; color:${color}; font-weight:${active ? 600 : 400};">
                <div style="height:8px; margin:0 3px 6px; border-radius:4px; background:${color};"></div>
                <span>${label}</span>
            </div>`;
        }).join("");
        const status_color = colors[current] || "#6b7280";
        frm.set_intro(`<div style="padding:8px 12px; border-left:4px solid ${status_color}; background:#f8fafc;">
            <div style="font-size:14px; margin-bottom:8px;"><b>Transfer status: ${current}</b></div>
            <div style="display:flex; width:100%; align-items:flex-start;">${steps}</div>
        </div>`, "blue");
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
