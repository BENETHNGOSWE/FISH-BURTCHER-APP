// Copyright (c) 2026 MANASE BUTCHER
// Fish POS - simple KG-based branch sales screen
frappe.pages["fish_pos"].on_page_load = function (wrapper) {
	frappe.require("assets/manase_butcher/css/manase_butcher.css");
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("🐟 Fish POS — MANASE BUTCHER"),
		single_column: true,
	});

	frappe.fish_pos = new FishPOS(page);
};

class FishPOS {
	constructor(page) {
		this.page = page;
		this.cart = [];
		this.payments = [];
		this.ctx = null;
		this.branch = null;
		this.make_layout();
		this.load_context();
	}

	make_layout() {
		const body = $(`
		<div class="fish-pos">
		  <div class="row">
		    <div class="col-md-7 fish-left">
		      <div class="fish-toolbar"></div>
		      <div class="fish-items-head">
		        <input class="form-control fish-search" placeholder="${__("Search fish by name…")}"/>
		      </div>
		      <div class="fish-grid"></div>
		    </div>
		    <div class="col-md-5 fish-right">
		      <div class="fish-cart-head"><h4>${__("Current Sale")}</h4></div>
		      <div class="fish-cart"></div>
		      <div class="fish-totals"></div>
		      <div class="fish-payments"></div>
		      <div class="fish-actions"></div>
		    </div>
		  </div>
		</div>`);
		this.page.main.html(body);
		this.toolbar = this.page.main.find(".fish-toolbar");
		this.search = this.page.main.find(".fish-search");
		this.grid = this.page.main.find(".fish-grid");
		this.cart_box = this.page.main.find(".fish-cart");
		this.totals_box = this.page.main.find(".fish-totals");
		this.pay_box = this.page.main.find(".fish-payments");
		this.actions_box = this.page.main.find(".fish-actions");
		this.search.on("input", () => this.load_items());
	}

	load_context() {
		return frappe
			.xcall("manase_butcher.fish_sales.api.pos.get_pos_context")
			.then((ctx) => {
				this.ctx = ctx;
				this.branch_field = this.page.add_field({
					label: __("Branch"),
					fieldtype: "Link",
					options: "Branch",
					fieldname: "branch",
					reqd: 1,
					default:
						frappe.defaults.get_user_default("Branch") ||
						(ctx.branches.length === 1 ? ctx.branches[0].name : ""),
					change: () => this.on_branch(),
				});
				this.branch_field.$input.find("input").attr(
					"data-in-filter", "1");
				// populate dropdown options
				this.branch_field.get_query = () => ({
					filters: { name: ["in", ctx.branches.map((b) => b.name)] },
				});
				this.price_field = this.page.add_field({
					label: __("Price Type"),
					fieldtype: "Select",
					options: ctx.price_types.join("\n"),
					default: "Retail",
					change: () => this.load_items(),
				});
				this.customer_field = this.page.add_field({
					label: __("Customer"),
					fieldtype: "Link",
					options: "Customer",
				});
				this.branch = this.branch_field.get_value();
				if (this.branch) this.on_branch();
			});
	}

	on_branch() {
		this.branch = this.branch_field.get_value();
		this.cart = [];
		this.payments = [];
		this.load_items();
		this.render_cart();
	}

	load_items() {
		if (!this.branch) {
			this.grid.html(
				`<div class="text-muted small padding">${__("Select your branch to start selling.")}</div>`
			);
			return Promise.resolve();
		}
		return frappe
			.xcall("manase_butcher.fish_sales.api.pos.get_branch_items", {
				branch: this.branch,
				search: this.search.val(),
				price_type: this.price_field.get_value(),
				customer: this.customer_field.get_value(),
			})
			.then((rows) => {
				this.grid.empty();
				if (!rows.length) {
					this.grid.html(`<div class="text-muted padding">${__("No fish found.")}</div>`);
					return;
				}
				rows.forEach((r) => {
					const cls = r.available_kg <= 0 ? "out" : "";
					const card = $(`
					<div class="fish-card ${cls}">
					  <div class="fish-card-img">🐟</div>
					  <div class="fish-card-name">${frappe.utils.escape_html(r.item_name)}</div>
					  <div class="fish-card-meta">${r.preparation || ""} · ${r.freshness || ""}</div>
					  <div class="fish-card-kg">${fmt(r.available_kg)} KG</div>
					  <div class="fish-card-price">${fmt_money(r.price_per_kg)} / KG</div>
					  <button class="btn btn-sm btn-primary add">${__("Add")}</button>
					</div>`);
					card.find(".add").on("click", () => {
						if (r.available_kg <= 0) {
							frappe.msgprint(__("Out of stock"));
							return;
						}
						this.prompt_kg(r);
					});
					this.grid.append(card);
				});
			});
	}

	prompt_kg(r) {
		const d = new frappe.ui.Dialog({
			title: r.item_name,
			fields: [
				{ fieldname: "kg", label: __("Weight (KG)"), fieldtype: "Float",
					options: "precision:3", reqd: 1, default: 1 },
				{ fieldname: "available", fieldtype: "HTML",
					label: "", options: `<div class="small text-muted">${__("Available")}: ${fmt(r.available_kg)} KG</div>` },
			],
			primary_action: (v) => {
				if (v.kg <= 0) return frappe.msgprint(__("Enter weight"));
				if (v.kg > r.available_kg)
					return frappe.msgprint(__("Only {0} KG available", [fmt(r.available_kg)]));
				this.add_line(r, v.kg);
				d.hide();
			},
		});
		d.show();
	}

	add_line(r, kg) {
		const existing = this.cart.find((l) => l.item === r.item);
		if (existing) {
			if (existing.kg + kg > r.available_kg)
				return frappe.msgprint(__("Only {0} KG available", [fmt(r.available_kg)]));
			existing.kg += kg;
		} else {
			this.cart.push({ item: r.item, name: r.item_name, kg, rate: r.price_per_kg });
		}
		this.render_cart();
	}

	line_total() {
		return this.cart.reduce((s, l) => s + l.kg * l.rate, 0);
	}

	render_cart() {
		this.cart_box.empty();
		if (!this.cart.length) {
			this.cart_box.html(`<div class="text-muted small padding">${__("Cart empty")}</div>`);
		}
		this.cart.forEach((l, i) => {
			const row = $(`
			<div class="fish-line">
			  <div>
			    <div>${frappe.utils.escape_html(l.name)}</div>
			    <div class="small text-muted">${fmt_money(l.rate)} / KG</div>
			  </div>
			  <div class="text-right">
			    <input class="form-control input-sm kg" style="width:90px;display:inline-block"
			           type="number" step="0.001" value="${l.kg}"/>
			    <div>${fmt_money(l.kg * l.rate)}</div>
			    <a class="del text-danger small">${__("remove")}</a>
			  </div>
			</div>`);
			row.find(".kg").on("change", (e) => {
				l.kg = parseFloat(e.target.value) || 0;
				this.render_cart();
			});
			row.find(".del").on("click", () => {
				this.cart.splice(i, 1);
				this.render_cart();
			});
			this.cart_box.append(row);
		});
		const total = this.line_total();
		this.totals_box.html(`
		<div class="fish-line"><strong>${__("Subtotal")}</strong><strong>${fmt_money(total)}</strong></div>
		<div class="fish-line"><span>${__("KG total")}</span><span>${fmt(this.cart.reduce((s, l) => s + l.kg, 0))}</span></div>`);
		this.render_payments(total);
	}

	render_payments(total) {
		this.pay_box.html(`<h5>${__("Payment")}</h5>`);
		const methods = (this.ctx?.payment_methods) ||
			["Cash", "M-Pesa", "Tigo Pesa", "Airtel Money", "HaloPesa", "Bank", "Card", "Credit"];
		methods.forEach((m) => {
			const row = $(`
			<div class="fish-line">
			  <span>${m}</span>
			  <span><input class="form-control input-sm pay" data-mode="${m}"
			    type="number" style="width:130px;display:inline-block" placeholder="0"/></span>
			</div>`);
			const inp = row.find("input");
			inp.on("input", () => this.update_change(total));
			this.pay_box.append(row);
		});
		this.actions_box.html(`
		<div class="fish-change"></div>
		<button class="btn btn-success btn-lg btn-block confirm">${__("Confirm Sale")}</button>`);
		this.actions_box.find(".confirm").on("click", () => this.confirm(total));
	}

	collect_payments() {
		const out = [];
		this.pay_box.find(".pay").each(function () {
			const amount = parseFloat(this.value) || 0;
			if (amount > 0)
				out.push({ mode: this.dataset.mode, amount, reference: "" });
		});
		return out;
	}

	update_change(total) {
		const paid = this.collect_payments().reduce((s, p) => s + p.amount, 0);
		const change = paid - total;
		this.actions_box.find(".fish-change").html(
			`<div class="fish-line"><strong>${__("Paid")}</strong><strong>${fmt_money(paid)}</strong></div>
			 <div class="fish-line ${change < 0 ? "text-danger" : ""}">
			   <strong>${change < 0 ? __("Outstanding") : __("Change")}</strong>
			   <strong>${fmt_money(Math.abs(change))}</strong></div>`);
	}

	confirm(total) {
		if (!this.branch) return frappe.msgprint(__("Select branch"));
		if (!this.cart.length) return frappe.msgprint(__("Cart empty"));
		const payments = this.collect_payments();
		const paid = payments.reduce((s, p) => (p.mode === "Credit" ? s : s + p.amount), 0);
		const has_credit = payments.some((p) => p.mode === "Credit");
		if (paid < total - 1 && !has_credit)
			return frappe.confirm(
				__("Payment is short by {0}. Continue as credit?", [fmt_money(total - paid)]),
				() => this.submit(payments, total));
		this.submit(payments, total);
	}

	submit(payments, total) {
		const payload = {
			branch: this.branch,
			customer: this.customer_field.get_value() || null,
			price_type: this.price_field.get_value(),
			items: this.cart.map((l) => ({ item: l.item, kg: l.kg })),
			payments: payments,
		};
		frappe
			.xcall("manase_butcher.fish_sales.api.pos.submit_sale", {
				data: JSON.stringify(payload),
			})
			.then((res) => {
				frappe.show_alert({ message: __("Sale {0} complete", [res.data.invoice]),
					indicator: "green" });
				this.cart = [];
				this.render_cart();
				this.load_items();
				frappe.set_route("Form", "Sales Invoice", res.data.invoice);
			});
	}
}

function fmt(v) {
	return (Math.round((v || 0) * 1000) / 1000).toLocaleString();
}
function fmt_money(v) {
	return (v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 }) + " TZS";
}
