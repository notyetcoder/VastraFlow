const APPAREL_SIZES = [22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52];
const APPAREL_SLEEVES = [
	{ code: 'H-S', label: 'Half Sleeve', fieldname: 'hs_qty' },
	{ code: 'F-S', label: 'Full Sleeve', fieldname: 'fs_qty' },
	{ code: 'S-L', label: 'Sleeveless', fieldname: 'sl_qty' }
];

// Front/Back/Sleeve locking rules driven by Sublimation Type.
// Any zone not listed here stays free but is restricted to
// Solid Color / Logo / A4 - it can never independently be "Sublimation".
const SUBLIMATION_LOCK_MAP = {
	'None': [],
	'Front Sublimation': ['front_print'],
	'Back Sublimation': ['back_print'],
	'Front & Back Sublimation': ['front_print', 'back_print'],
	'Full Sublimation': ['front_print', 'back_print', 'sleeve_print']
};
const FREE_ZONE_OPTIONS = ['Solid Color', 'Logo', 'A4'];
const ZONE_COLOUR_FIELD = { front_print: 'front_colour', back_print: 'back_colour', sleeve_print: 'sleeve_colour' };
const ZONE_LABEL = { front_print: 'Front', back_print: 'Back', sleeve_print: 'Sleeves' };

frappe.ui.form.on('P3 Order Book', {
	setup(frm) {
		// Item Attribute Value is a CHILD TABLE of Item Attribute - it has no
		// "attribute" column. The column that actually links a value back to
		// its owning attribute is Frappe's standard child-table column
		// "parent" (holding the Item Attribute's name, e.g. "Fabric").
		frm.set_query('fabric', () => ({ filters: { parent: 'Fabric' } }));
		frm.set_query('stitching', () => ({ filters: { parent: 'Stitching' } }));
		['front_colour', 'back_colour', 'sleeve_colour'].forEach(f => {
			frm.set_query(f, () => ({ filters: { parent: 'Colour' } }));
		});
		// Collar Type variants live under the parent template Item "Collar" -
		// filtering by variant_of is the correct/robust way to pull all of
		// them, regardless of what Item Group each variant ends up in.
		frm.set_query('collar_type', () => ({ filters: { variant_of: 'Collar' } }));
		frm.set_query('product_type', () => ({ filters: { item_group: 'Products' } }));

	},

	refresh(frm) {
		frm.trigger('render_matrix_grid');
		frm.trigger('render_artwork_preview');
		frm.trigger('render_collar_preview');
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
		// Sales Order itself calls - rather than reinventing address/contact
		// fetch logic.
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

	collar_type(frm) {
		frm.trigger('render_collar_preview');
	},

	render_collar_preview(frm) {
		let $wrapper = frm.fields_dict.collar_preview.$wrapper;
		if (!frm.doc.collar_type) {
			$wrapper.html('');
			return;
		}
		frappe.db.get_value('Item', frm.doc.collar_type, 'image').then(r => {
			let image = r.message && r.message.image;
			$wrapper.html(
				image
					? `<img src="${frappe.utils.escape_html(image)}" style="max-height:120px; border:1px solid var(--border-color, #d1d8dd); border-radius:6px; padding:4px; margin-top:4px;" />`
					: `<span style="font-size:11px; color:#8d99a6;">No image uploaded for this collar variant yet.</span>`
			);
		});
	},

	sublimation_type(frm) {
		frm.trigger('apply_sublimation_lock');
	},

	apply_sublimation_lock(frm) {
		let locked = SUBLIMATION_LOCK_MAP[frm.doc.sublimation_type] || [];

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
		let $wrapper = frm.fields_dict.artwork_preview_html.$wrapper;
		if (!frm.doc.artwork_file) {
			$wrapper.html(`<span style="font-size:11px; color:#8d99a6;">No artwork attached.</span>`);
			return;
		}
		// Small thumbnail by default; hover to see it full size - pure CSS,
		// no click/modal needed.
		$wrapper.html(`
			<div class="p3o-artwork-hover" style="position:relative; display:inline-block;">
				<img src="${frappe.utils.escape_html(frm.doc.artwork_file)}"
				     style="width:70px; height:70px; object-fit:cover; border:1px solid #d1d8dd; border-radius:6px; cursor:zoom-in;" />
				<img src="${frappe.utils.escape_html(frm.doc.artwork_file)}"
				     class="p3o-artwork-full"
				     style="display:none; position:absolute; top:0; left:80px; z-index:50; max-width:320px; max-height:320px;
				            border:1px solid #d1d8dd; border-radius:6px; box-shadow:0 4px 18px rgba(0,0,0,.18); background:#fff; padding:4px;" />
			</div>
		`);
		$wrapper.find('.p3o-artwork-hover')
			.on('mouseenter', function () { $(this).find('.p3o-artwork-full').show(); })
			.on('mouseleave', function () { $(this).find('.p3o-artwork-full').hide(); });
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
			// Returning a rejected promise here blocks the submit until the
			// user explicitly confirms - asked once, as requested.
			return new Promise((resolve, reject) => {
				frappe.confirm(
					__('This order uses sublimation but no artwork file is attached. Submit anyway?'),
					() => resolve(),
					() => reject()
				);
			});
		}
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
