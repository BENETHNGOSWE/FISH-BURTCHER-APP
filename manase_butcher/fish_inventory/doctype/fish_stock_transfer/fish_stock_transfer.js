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
        // Keep the process indicator in the form header, beside ERPNext's
        // Submitted pill, rather than adding a large block above the form.
        frm.set_intro("");
        const wrapper = frm.page.wrapper;
        wrapper.find(".mb-transfer-stepper").remove();

        const labels = ["Submitted", "Approved", "Dispatched", "Completed"];
        const raw_status = frm.doc.status || "Draft";
        const current = raw_status === "Received" ? "Completed" : raw_status;
        const cancelled = raw_status === "Cancelled";
        const current_index = labels.indexOf(current);
        const colors = ["#55d6d1", "#3ec9c5", "#35b7e9", "#17558f"];
        const active_color = cancelled ? "#ef4444" : "#35b7e9";

        const step_html = labels.map((label, index) => {
            const active = !cancelled && current_index >= index;
            const color = active ? colors[index] : "#d7dce2";
            const text_color = active ? "#ffffff" : "#8c98a6";
            return `<span style="display:inline-flex; align-items:center; justify-content:center;
                min-width:88px; height:28px; margin-right:4px; padding:0 18px 0 14px;
                color:${text_color}; background:${color}; font-size:11px; font-weight:600;
                clip-path:polygon(0 0, calc(100% - 12px) 0, 100% 50%, calc(100% - 12px) 100%, 0 100%, 12px 50%);">
                ${label}
            </span>`;
        }).join("");
        const cancelled_html = cancelled ? `<span style="display:inline-flex; align-items:center;
            height:28px; padding:0 18px; color:#fff; background:#ef4444; font-size:11px;
            font-weight:600; border-radius:4px;">Cancelled</span>` : "";
        const status_label = cancelled ? "Cancelled" : current;
        const stepper = $(`<div class="mb-transfer-stepper" title="Transfer status: ${status_label}"
            style="display:flex; align-items:center; margin-left:16px; white-space:nowrap;">
            ${step_html}${cancelled_html}
        </div>`);

        const header = wrapper.find(".page-head .page-head-content").first();
        if (!header.length) return;
        const indicator = header.find(".indicator-pill, .indicator").first();
        if (indicator.length) {
            indicator.after(stepper);
        } else {
            header.append(stepper);
        }
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
