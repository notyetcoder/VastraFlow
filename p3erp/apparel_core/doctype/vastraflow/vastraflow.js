// NOTE ON SAVE vs SUBMIT: this file deliberately never touches
// frm.page.set_primary_action, disable_save, or anything else that would
// override Frappe's own toolbar logic. The standard Frappe behavior -
// primary button reads "Save" whenever the doc is dirty, and only offers
// "Submit" on a clean, already-saved, submittable draft - is left
// completely untouched. Every matrix edit calls frm.dirty() (see
// render_matrix_grid below), which is what correctly flips the primary
// button back to "Save" the moment something changes after a save. The
// "Create Sales Order" custom button is intentionally added as a
// SECONDARY button (frm.add_custom_button), never as the primary action,
// and only appears post-submit - it can never be confused with Save/Submit.
const APPAREL_SIZES = [22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54];
const APPAREL_SLEEVES = [
	{ code: 'H-S', label: 'Half Sleeve', fieldname: 'hs_qty' },
	{ code: 'F-S', label: 'Full Sleeve', fieldname: 'fs_qty' },
	{ code: 'S-L', label: 'Sleeveless', fieldname: 'sl_qty' }
];

const FREE_ZONE_OPTIONS = ['Solid Color', 'Logo', 'A4'];
const ZONE_COLOUR_FIELD = { front_print: 'front_colour', back_print: 'back_colour', sleeve_print: 'sleeve_colour' };

// Keyword-matched, same logic as the server-side _locked_zones_for() in
// vastraflow.py - deliberately NOT an exact-string map, since real
// Sublimation Type values in ERPNext have inconsistent casing/spacing
// ("Full sublimation" vs "Front & Back sublimation" etc.).
function locked_zones_for(sublimation_type) {
	let value = (sublimation_type || '').toLowerCase();
	if (value.includes('full')) return ['front_print', 'back_print', 'sleeve_print'];
	if (value.includes('front') && value.includes('back')) return ['front_print', 'back_print'];
	if (value.includes('front')) return ['front_print'];
	if (value.includes('back')) return ['back_print'];
	return [];
}

// Dynamic-Select fields populated live from ERPNext's own Item Attribute
// data (never hardcoded, never linked directly to Item Attribute Value's
// internal hash IDs - see apparel_core/api.py docstring for why).
const DYNAMIC_SELECT_FIELDS = {
	stitching: 'Stitching',
	front_colour: 'Colour',
	back_colour: 'Colour',
	sleeve_colour: 'Colour',
	collar_colour: 'Colour',
	border_colour: 'Colour',
	sublimation_type: 'Sublimation'
};

frappe.ui.form.on('VastraFlow', {
	setup(frm) {
		// "Most used first" ranked Link queries - real usage-frequency
		// ranking via apparel_core/api.py, not just alphabetical.
		frm.set_query('product_type', () => ({
			query: 'p3erp.apparel_core.api.item_link_query',
			filters: { item_group: 'Products', _usage_fieldname: 'product_type' }
		}));
		frm.set_query('fabric', () => ({
			query: 'p3erp.apparel_core.api.item_link_query',
			filters: { variant_of: 'FB', _usage_fieldname: 'fabric', _attribute_name: 'Fabric' }
		}));
		frm.set_query('collar_type', () => ({
			query: 'p3erp.apparel_core.api.item_link_query',
			filters: { variant_of: 'COLL', _usage_fieldname: 'collar_type', _attribute_name: 'Collar Type' }
		}));
	},

	onload(frm) {
		frm.trigger('load_dynamic_select_options');
	},

	load_dynamic_select_options(frm) {
		Object.entries(DYNAMIC_SELECT_FIELDS).forEach(([fieldname, attribute]) => {
			frappe.call({
				method: 'p3erp.apparel_core.api.get_attribute_values',
				args: { attribute },
				callback(r) {
					let values = r.message || [];
					let blank_ok = ['front_colour', 'back_colour', 'sleeve_colour', 'collar_colour', 'border_colour', 'stitching'].includes(fieldname);
					frm.set_df_property(fieldname, 'options', (blank_ok ? [''] : []).concat(values).join('\n'));
					frm.refresh_field(fieldname);
				}
			});
		});
	},

	refresh(frm) {
		frm.trigger('render_matrix_grid');
		frm.trigger('render_artwork_preview');
		frm.trigger('render_collar_preview');
		frm.trigger('render_fabric_preview');
		frm.trigger('apply_sublimation_lock');
		frm.trigger('toggle_colour_fields');
		frm.trigger('render_create_so_button');
	},

	customer(frm) {
		if (!frm.doc.customer) {
			frm.set_value('customer_address', '');
			frm.set_value('address_display', '');
			frm.set_value('contact_person', '');
			frm.set_value('contact_display', '');
			return;
		}
		// Reuses ERPNext's own party-details endpoint - the exact same one
		// Sales Order itself calls.
		frappe.call({
			method: 'erpnext.accounts.party.get_party_details',
			args: { party: frm.doc.customer, party_type: 'Customer' },
			callback(r) {
				if (!r.message) return;
				frm.set_value('customer_address', r.message.customer_address);
				frm.set_value('address_display', r.message.address_display);
				frm.set_value('contact_person', r.message.contact_person);
				frm.set_value('contact_display', r.message.contact_display);
			}
		});
	},

	fabric(frm) { frm.trigger('render_fabric_preview'); },
	collar_type(frm) { frm.trigger('render_collar_preview'); },

	render_fabric_preview(frm) {
		frm.trigger('_render_variant_preview', { fieldname: 'fabric', attribute: 'Fabric', wrapper: 'fabric_preview' });
	},

	render_collar_preview(frm) {
		frm.trigger('_render_variant_preview', { fieldname: 'collar_type', attribute: 'Collar Type', wrapper: 'collar_preview' });
	},

	_render_variant_preview(frm, { fieldname, attribute, wrapper }) {
		let $wrapper = frm.fields_dict[wrapper].$wrapper;
		let item_code = frm.doc[fieldname];

		if (!item_code) {
			$wrapper.html('');
			return;
		}

		// Image straight off the Item.
		frappe.db.get_value('Item', item_code, 'image').then(r => {
			let image = r.message && r.message.image;
			let img_html = image
				? `<img src="${frappe.utils.escape_html(image)}" style="max-height:120px; border:1px solid var(--border-color, #d1d8dd); border-radius:6px; padding:4px; margin-top:4px;" />`
				: `<span style="font-size:11px; color:#8d99a6;">No image uploaded for this variant yet.</span>`;
			$wrapper.html(img_html + '<div class="variant-label" style="font-size:11px; color:#6b7580; margin-top:4px;">Resolving name&hellip;</div>');

			// Real human name straight off the Item's own variant
			// attributes - not item_name/item_code, which may just be a
			// short internal code like "Fabric-CM" rather than "Soft
			// Micro". Same lookup logic as resolve_variant_labels() on
			// the server, done live here for immediate feedback before
			// the doc is even saved.
			frappe.db.get_list('Item Variant Attribute', {
				filters: { parent: item_code, attribute: attribute },
				fields: ['attribute_value'],
				limit: 1
			}).then(rows => {
				let label = rows && rows[0] && rows[0].attribute_value;
				$wrapper.find('.variant-label').html(
					label ? `Selected: <strong>${frappe.utils.escape_html(label)}</strong>` : ''
				);
			});
		});
	},

	sublimation_type(frm) {
		frm.trigger('apply_sublimation_lock');
	},

	apply_sublimation_lock(frm) {
		let locked = locked_zones_for(frm.doc.sublimation_type);

		['front_print', 'back_print', 'sleeve_print'].forEach(zone => {
			if (locked.includes(zone)) {
				frm.set_df_property(zone, 'options', 'Sublimation');
				if (frm.doc[zone] !== 'Sublimation') frm.set_value(zone, 'Sublimation');
				frm.set_df_property(zone, 'read_only', 1);
			} else {
				frm.set_df_property(zone, 'options', FREE_ZONE_OPTIONS.join('\n'));
				frm.set_df_property(zone, 'read_only', 0);
				if (frm.doc[zone] === 'Sublimation') frm.set_value(zone, '');
			}
		});
		frm.trigger('toggle_colour_fields');
	},

	front_print(frm) { frm.trigger('toggle_colour_fields'); },
	back_print(frm) { frm.trigger('toggle_colour_fields'); },
	sleeve_print(frm) { frm.trigger('toggle_colour_fields'); },

	toggle_colour_fields(frm) {
		Object.entries(ZONE_COLOUR_FIELD).forEach(([zone, colour_field]) => {
			let show = frm.doc[zone] === 'Solid Color';
			frm.set_df_property(colour_field, 'hidden', show ? 0 : 1);
			frm.set_df_property(colour_field, 'reqd', show ? 1 : 0);
			if (!show) frm.set_value(colour_field, '');
		});
	},

	artwork_file(frm) {
		frm.trigger('render_artwork_preview');
	},

	render_artwork_preview(frm) {
		// Hover-to-zoom lives ONLY here, on the live data-entry form. Print
		// preview and the final print show the artwork as a full-size
		// image directly - see production_job_card.html.
		let $wrapper = frm.fields_dict.artwork_preview_html.$wrapper;
		if (!frm.doc.artwork_file) {
			$wrapper.html(`<span style="font-size:11px; color:#8d99a6;">No artwork attached.</span>`);
			return;
		}

		let file_url = frm.doc.artwork_file;
		let file_name = file_url.split('/').pop();

		$wrapper.html(`
			<style>
				.p3o-art-thumb { width:78px; height:78px; object-fit:cover; border:1px solid #d1d8dd;
					border-radius:8px; cursor:zoom-in; display:block;
					transition: transform .15s ease, box-shadow .15s ease; }
				.p3o-art-hover:hover .p3o-art-thumb { transform: scale(1.04); box-shadow: 0 2px 10px rgba(0,0,0,.12); }
				.p3o-art-full-wrap { display:none; opacity:0; position:absolute; z-index:60;
					transition: opacity .15s ease, transform .15s ease; transform: translateY(4px) scale(.98);
					background:#fff; border:1px solid #d1d8dd; border-radius:10px;
					box-shadow: 0 12px 32px rgba(0,0,0,.22); padding:8px; }
				.p3o-art-full-wrap.p3o-show { display:block; }
				.p3o-art-full-wrap img { max-width:340px; max-height:340px; display:block; border-radius:6px; }
				.p3o-art-caption { font-size:10.5px; color:#6b7580; margin-top:6px; text-align:center;
					max-width:340px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
			</style>
			<div class="p3o-art-hover" style="position:relative; display:inline-block;">
				<img class="p3o-art-thumb" src="${frappe.utils.escape_html(file_url)}" />
				<div class="p3o-art-full-wrap">
					<img src="${frappe.utils.escape_html(file_url)}" />
					<div class="p3o-art-caption">${frappe.utils.escape_html(file_name)}</div>
				</div>
			</div>
		`);

		let $hover = $wrapper.find('.p3o-art-hover');
		let $full = $wrapper.find('.p3o-art-full-wrap');

		$hover.on('mouseenter', function () {
			// Edge-aware placement: open to the right by default, flip to
			// the left if there isn't enough room (e.g. narrow sidebar).
			let hover_rect = $hover[0].getBoundingClientRect();
			let opens_right = hover_rect.left + 90 + 340 < window.innerWidth;
			$full.css({
				top: 0,
				left: opens_right ? '90px' : 'auto',
				right: opens_right ? 'auto' : '90px'
			});
			$full.addClass('p3o-show');
			requestAnimationFrame(() => $full.css({ opacity: 1, transform: 'translateY(0) scale(1)' }));
		});
		$hover.on('mouseleave', function () {
			$full.css({ opacity: 0, transform: 'translateY(4px) scale(.98)' });
			setTimeout(() => $full.removeClass('p3o-show'), 150);
		});
	},

	render_create_so_button(frm) {
		frm.remove_custom_button('Create Sales Order');
		if (frm.doc.docstatus !== 1) return;

		if (frm.doc.sales_order_status === 'Submitted') {
			frm.dashboard.set_headline_alert(
				`<a href="/app/sales-order/${frm.doc.sales_order}">Sales Order ${frm.doc.sales_order} — Submitted</a>`,
				'green'
			);
			return;
		}

		frm.add_custom_button('Create Sales Order', () => {
			frappe.confirm(
				__('This will submit Sales Order {0} for real - it becomes official and shows up in all Sales Order reports/lists. Continue?', [frm.doc.sales_order]),
				() => {
					frm.call('create_sales_order_from_book').then(() => frm.reload_doc());
				}
			);
		}).addClass('btn-primary');
	},

	before_submit(frm) {
		let any_sublimation = ['front_print', 'back_print', 'sleeve_print'].some(f => frm.doc[f] === 'Sublimation');
		if (any_sublimation && !frm.doc.artwork_file) {
			let artwork_ok = new Promise((resolve, reject) => {
				frappe.confirm(
					__('This order uses sublimation but no artwork file is attached. Submit anyway?'),
					() => resolve(),
					() => reject()
				);
			});
			return artwork_ok.then(() => frm.trigger('check_pricing_before_submit'));
		}
		return frm.trigger('check_pricing_before_submit');
	},

	// Only relevant for Account Managers - everyone else just lets the
	// server's own before_submit throw its normal blocking error, which
	// already lists every missing combination clearly. This is purely a
	// client-side convenience so an Account Manager doesn't have to fail
	// a submit, go find the Base Price list, and come back - it opens
	// Frappe's own standard "New" quick-entry dialog, prefilled, exactly
	// the way Frappe itself prompts for a missing dependency elsewhere.
	check_pricing_before_submit(frm) {
		if (!frappe.user_roles.includes('Account Manager')) {
			return Promise.resolve();
		}

		return frm.call('get_missing_price_prefill').then(r => {
			let prefill = r.message;
			if (!prefill) {
				return; // nothing missing - let submit proceed normally
			}

			return new Promise((resolve, reject) => {
				frappe.msgprint({
					title: __('Pricing needed'),
					message: __('No Base Price found for Fabric "{0}". Add one now, then click Submit again.', [prefill.rule_name]),
					indicator: 'orange'
				});
				frappe.new_doc('P3 Base Price', prefill);
				// frappe.new_doc opens the standard quick-entry/full form -
				// whether the user actually saves it or cancels, either way
				// we stop THIS submit attempt here; they click Submit again
				// once pricing exists.
				reject();
			});
		});
	},

	// The size_matrix Table field (hidden) is the real data store; the
	// visual grid below renders it and keeps it in sync on every change.
	render_matrix_grid(frm) {
		let existing = {};
		(frm.doc.size_matrix || []).forEach(row => { existing[row.size_code] = row; });

		let html = `
            <div style="overflow-x:auto; margin:10px 0;">
                <table class="table table-bordered table-sm" style="text-align:center; background:#fff; font-size:12px;">
                    <thead style="background:#171717; color:#fff;">
                        <tr>
                            <th style="min-width:100px;">Sleeve Type</th>
                            ${APPAREL_SIZES.map(s => `<th style="min-width:38px;">${s}</th>`).join('')}
                            <th style="min-width:56px; background:#3a3a3a;">Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${APPAREL_SLEEVES.map(sleeve => `
                            <tr>
                                <td style="font-weight:700; text-align:left; vertical-align:middle;">${sleeve.label}</td>
                                ${APPAREL_SIZES.map(size => `
                                    <td style="padding:2px;">
                                        <input type="number"
                                               class="form-control form-control-sm matrix-input"
                                               data-sleeve="${sleeve.code}"
                                               data-fieldname="${sleeve.fieldname}"
                                               data-size="${size}"
                                               min="0"
                                               value="${(existing[size] && existing[size][sleeve.fieldname]) || ''}"
                                               ${frm.doc.docstatus !== 0 ? 'disabled' : ''}
                                               style="text-align:center; padding:2px; height:26px;" />
                                    </td>
                                `).join('')}
                                <td class="sleeve-total" data-sleeve="${sleeve.code}" style="font-weight:700; background:#f1f5f9; vertical-align:middle;">0</td>
                            </tr>
                        `).join('')}
                    </tbody>
                    <tfoot style="background:#e2e8f0; font-weight:700;">
                        <tr>
                            <td>Size Total</td>
                            ${APPAREL_SIZES.map(size => `<td class="size-total" data-size="${size}">0</td>`).join('')}
                            <td id="grand-matrix-total" style="background:#cbd5e1; font-size:13px; color:#2490ef;">0</td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        `;

		let $wrapper = frm.fields_dict.size_sleeve_html.$wrapper;
		$wrapper.html(html);

		let recalc = () => {
			let total = 0;
			APPAREL_SLEEVES.forEach(slv => {
				let slv_tot = 0;
				$wrapper.find(`.matrix-input[data-sleeve="${slv.code}"]`).each(function () {
					slv_tot += parseInt($(this).val(), 10) || 0;
				});
				$wrapper.find(`.sleeve-total[data-sleeve="${slv.code}"]`).text(slv_tot);
			});
			APPAREL_SIZES.forEach(sz => {
				let sz_tot = 0;
				$wrapper.find(`.matrix-input[data-size="${sz}"]`).each(function () {
					sz_tot += parseInt($(this).val(), 10) || 0;
				});
				$wrapper.find(`.size-total[data-size="${sz}"]`).text(sz_tot);
				total += sz_tot;
			});
			$wrapper.find('#grand-matrix-total').text(total);
			frm.set_value('total_qty', total);
		};

		let sync_to_doc = (size, fieldname, value) => {
			let row = (frm.doc.size_matrix || []).find(r => r.size_code === String(size));
			if (!row) row = frm.add_child('size_matrix', { size_code: String(size) });
			row[fieldname] = cint(value) || 0;
			row.total_qty = (row.hs_qty || 0) + (row.fs_qty || 0) + (row.sl_qty || 0);
			frm.dirty();
		};

		let debounced_handler = frappe.utils.debounce(function () {
			let $input = $(this);
			sync_to_doc($input.data('size'), $input.data('fieldname'), $input.val());
			recalc();
		}, 250);

		$wrapper.find('.matrix-input').on('input', debounced_handler);
		recalc();
	}
});
