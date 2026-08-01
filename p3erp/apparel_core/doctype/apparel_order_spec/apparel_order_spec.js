const APPAREL_SIZES = [22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54];
const APPAREL_SLEEVES = [
	{ code: 'H-S', label: 'Half Sleeve', fieldname: 'hs_qty' },
	{ code: 'F-S', label: 'Full Sleeve', fieldname: 'fs_qty' },
	{ code: 'S-L', label: 'Sleeveless', fieldname: 'sl_qty' }
];

frappe.ui.form.on('Apparel Order Spec', {
	setup(frm) {
		// Restrict attribute-value pickers to the correct Item Attribute so
		// users aren't shown every attribute value in the system (e.g. sizes,
		// colours belonging to unrelated attributes) in the Fabric/Collar/
		// Solid Colour dropdowns.
		frm.set_query('fabric', () => ({ filters: { attribute: 'Fabric' } }));
		frm.set_query('collar_type', () => ({ filters: { attribute: 'Collar Type' } }));
		frm.set_query('solid_colour', () => ({ filters: { attribute: 'Colour' } }));
	},

	refresh(frm) {
		frm.trigger('render_matrix_grid');
		frm.trigger('setup_artwork_preview');

		if (frm.doc.docstatus === 1) {
			frm.dashboard.set_headline(
				__('Routed via {0} strategy.', [frm.doc.bom_strategy])
			);
		}
	},

	print_sublimation_type(frm) {
		if (frm.doc.print_sublimation_type === 'Full Sublimation') {
			frm.set_df_property('solid_colour', 'hidden', 1);
			frm.set_df_property('solid_colour', 'reqd', 0);
			frm.set_value('solid_colour', '');
		} else {
			frm.set_df_property('solid_colour', 'hidden', 0);
		}
	},

	artwork_file(frm) {
		frm.trigger('update_artwork_preview');
	},

	setup_artwork_preview(frm) {
		if ($('#artwork-sidebar-preview').length === 0) {
			let box_html = `
                <div id="artwork-sidebar-preview" style="margin-top:15px; padding:10px; border:1px solid #cbd5e1; border-radius:8px; background:#f8fafc; text-align:center;">
                    <h6 style="font-weight:700; color:#0f172a; margin-bottom:8px; font-size:12px;">LIVE ARTWORK PREVIEW</h6>
                    <div id="artwork-img-container" style="min-height:160px; max-height:220px; display:flex; align-items:center; justify-content:center; border:1px dashed #94a3b8; border-radius:6px; background:#fff;">
                        <span style="color:#94a3b8; font-size:11px;">No File Uploaded</span>
                    </div>
                </div>
            `;
			frm.sidebar.wrapper.find('.form-sidebar-stats').append(box_html);
		}
		frm.trigger('update_artwork_preview');
	},

	update_artwork_preview(frm) {
		let container = $('#artwork-img-container');
		if (frm.doc.artwork_file) {
			container.html(
				`<img src="${frappe.utils.escape_html(frm.doc.artwork_file)}" style="max-width:100%; max-height:200px; object-fit:contain; padding:4px;" />`
			);
		} else {
			container.html(`<span style="color:#94a3b8; font-size:11px;">No File Uploaded</span>`);
		}
	},

	// The size_matrix Table field (hidden) is the actual data store.
	// This renders it as a compact matrix and keeps the two in sync,
	// instead of the old approach where the grid was purely visual and
	// nothing typed into it was ever saved to the document.
	render_matrix_grid(frm) {
		let existing = {};
		(frm.doc.size_matrix || []).forEach(row => {
			existing[row.size_code] = row;
		});

		let html = `
            <div style="overflow-x:auto; margin:10px 0;">
                <table class="table table-bordered table-sm" style="text-align:center; background:#fff; font-size:12px;">
                    <thead style="background:#0f172a; color:#fff;">
                        <tr>
                            <th style="min-width:100px;">Sleeve Type</th>
                            ${APPAREL_SIZES.map(s => `<th style="min-width:40px;">${s}</th>`).join('')}
                            <th style="min-width:60px; background:#334155;">Total</th>
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
                                               style="text-align:center; padding:2px; height:28px;" />
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
                            <td id="grand-matrix-total" style="background:#cbd5e1; font-size:13px; color:#0284c7;">0</td>
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

		// Push a single input's value into the real (hidden) size_matrix
		// child table row so it actually gets saved with the document.
		let sync_to_doc = (size, fieldname, value) => {
			let row = (frm.doc.size_matrix || []).find(r => r.size_code === String(size));
			if (!row) {
				row = frm.add_child('size_matrix', { size_code: String(size) });
			}
			row[fieldname] = cint(value) || 0;
			row.total_qty = (row.hs_qty || 0) + (row.fs_qty || 0) + (row.sl_qty || 0);
			frm.dirty();
		};

		// Debounce so a rapid burst of keystrokes doesn't trigger a full
		// grid recalculation + doc sync on every single keystroke.
		let debounced_handler = frappe.utils.debounce(function () {
			let $input = $(this);
			sync_to_doc($input.data('size'), $input.data('fieldname'), $input.val());
			recalc();
		}, 250);

		$wrapper.find('.matrix-input').on('input', debounced_handler);

		recalc();
	}
});
