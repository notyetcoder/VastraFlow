frappe.pages['price-calculator'].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Price Calculator',
		single_column: true
	});

	new PriceCalculator(page);
};

class PriceCalculator {
	constructor(page) {
		this.page = page;
		this.spec_values = {};
		this.render();
	}

	render() {
		this.$wrapper = $(`
			<div style="max-width:760px; margin:20px auto; font-family:inherit;">
				<div style="background:#fafbfb; border:1px solid #dfe3e6; border-radius:8px; padding:20px; margin-bottom:16px;">
					<p style="font-size:11px; color:#6b7580; margin:0 0 14px;">
						Live simulator using the exact same pricing logic real orders use - nothing shown here can drift from what an order actually gets charged.
					</p>
					<div class="calc-grid" style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
						<div><label style="font-size:11px; font-weight:600; color:#495057;">Product Type</label>
							<input type="text" class="form-control" data-field="product_type" placeholder="Link to Item..." /></div>
						<div><label style="font-size:11px; font-weight:600; color:#495057;">Fabric <span style="color:#d9364a;">*</span></label>
							<input type="text" class="form-control" data-field="fabric" placeholder="Link to Item..." /></div>
						<div><label style="font-size:11px; font-weight:600; color:#495057;">Customer (optional)</label>
							<input type="text" class="form-control" data-field="customer" placeholder="Link to Customer..." /></div>
						<div><label style="font-size:11px; font-weight:600; color:#495057;">Size</label>
							<select class="form-control" data-field="Size">
								<option value="">-</option>
								${[22,24,26,28,30,32,34,36,38,40,42,44,46,48,50,52,54].map(s => `<option value="${s}">${s}</option>`).join('')}
							</select></div>
						<div><label style="font-size:11px; font-weight:600; color:#495057;">Sleeve Type</label>
							<select class="form-control" data-field="Sleeve Type">
								<option value="">-</option>
								<option>Half Sleeve</option><option>Full Sleeve</option><option>Sleeveless</option>
							</select></div>
						<div><label style="font-size:11px; font-weight:600; color:#495057;">Sublimation</label>
							<select class="form-control" data-field="Sublimation"><option value="">-</option></select></div>
					</div>
				</div>

				<div id="calc-result"></div>
			</div>
		`);
		this.page.main.append(this.$wrapper);

		// Link fields need real Frappe link-search behavior - use the same
		// query functions the real order form uses, so results here match
		// exactly (same filters, same "most used first" ranking).
		this.make_link_control('product_type', 'Item', { query: 'p3erp.apparel_core.api.item_link_query', filters: { item_group: 'Products' } });
		this.make_link_control('fabric', 'Item', { query: 'p3erp.apparel_core.api.item_link_query', filters: { variant_of: 'FB', _attribute_name: 'Fabric' } });
		this.make_link_control('customer', 'Customer', {});

		frappe.call({ method: 'p3erp.apparel_core.api.get_attribute_values', args: { attribute: 'Sublimation' } })
			.then(r => {
				let $sel = this.$wrapper.find('[data-field="Sublimation"]');
				(r.message || []).forEach(v => $sel.append(`<option>${frappe.utils.escape_html(v)}</option>`));
			});

		this.$wrapper.find('select[data-field]').on('change', () => this.recalculate());
	}

	make_link_control(fieldname, doctype, query_opts) {
		let $input = this.$wrapper.find(`[data-field="${fieldname}"]`);
		let control = frappe.ui.form.make_control({
			parent: $input.parent(),
			df: {
				fieldtype: 'Link',
				fieldname: fieldname,
				options: doctype,
				get_query: () => query_opts.query ? { query: query_opts.query, filters: query_opts.filters } : {}
			},
			render_input: true
		});
		$input.remove();
		control.$input.on('change', () => {
			this[fieldname] = control.get_value();
			this.recalculate();
		});
		control.refresh();
	}

	recalculate() {
		let fabric = this.fabric;
		if (!fabric) {
			this.$wrapper.find('#calc-result').html(
				`<div style="text-align:center; padding:30px; color:#94a3b8; font-size:12px;">Select a Fabric to see pricing.</div>`
			);
			return;
		}

		let spec_values = {};
		this.$wrapper.find('select[data-field]').each(function () {
			let field = $(this).data('field');
			let val = $(this).val();
			if (val) spec_values[field] = val;
		});

		frappe.call({
			method: 'p3erp.apparel_core.pricing.calculate_price_api',
			args: {
				fabric: fabric,
				product_type: this.product_type || null,
				customer: this.customer || null,
				spec_values: JSON.stringify(spec_values)
			}
		}).then(r => this.render_result(r.message));
	}

	render_result(result) {
		let rows = result.adjustments.map(a => `
			<tr>
				<td>${frappe.utils.escape_html(a.attribute)}: ${frappe.utils.escape_html(a.value)}</td>
				<td style="text-align:right;">
					${!a.price_enabled
						? `<span style="color:#94a3b8;">Not price-enabled</span>`
						: (a.matched ? `+${a.amount}` : `<span style="color:#94a3b8;">No adjustment set (+0)</span>`)}
				</td>
			</tr>
		`).join('');

		let html = result.missing_base_price
			? `<div style="background:#fff8e6; border:1px solid #f0d78c; border-radius:8px; padding:16px; text-align:center; color:#7a5c00; font-size:12.5px;">
				No Base Price found for this Fabric${this.product_type ? ' + Product Type' : ''}${this.customer ? ' + Customer' : ''} combination.
				An order with this exact spec would be blocked at Submit.
			   </div>`
			: `<div style="background:#fff; border:1px solid #dfe3e6; border-radius:8px; padding:16px;">
				<div style="display:flex; justify-content:space-between; font-size:12.5px; padding:6px 0; border-bottom:1px dashed #dfe3e6;">
					<span>Base Rate <span style="color:#6b7580; font-size:10.5px;">(${frappe.utils.escape_html(result.base_source)})</span></span>
					<span style="font-weight:700;">${result.base_rate}</span>
				</div>
				<table style="width:100%; font-size:12px; margin-top:4px;">${rows}</table>
				<div style="display:flex; justify-content:space-between; margin-top:10px; padding-top:10px; border-top:2px solid #111417; font-size:15px; font-weight:800;">
					<span>Total</span>
					<span style="color:#2490ef;">${result.currency} ${result.total}</span>
				</div>
			   </div>`;

		this.$wrapper.find('#calc-result').html(html);
	}
}
