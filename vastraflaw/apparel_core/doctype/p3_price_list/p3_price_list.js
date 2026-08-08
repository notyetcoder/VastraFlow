frappe.ui.form.on('P3 Price List', {
	onload: function (frm) {
		// Sublimation Type options come from the real "Sublimation" Item
		// Attribute at runtime - never hardcoded here. Same source and
		// same helper the Order Book form itself uses, so the two can
		// never drift out of sync with each other.
		frappe.call({
			method: 'vastraflaw.apparel_core.api.get_attribute_values',
			args: { attribute: 'Sublimation' },
		}).then((r) => {
			let values = r.message || [];
			frm.set_df_property('sublimation_type', 'options', [''].concat(values).join('\n'));
			frm.refresh_field('sublimation_type');
		});

		// Fabric uses the exact same "most used first" variant-scoped
		// query as the Order Book's own Fabric field.
		frm.set_query('fabric', () => ({
			query: 'vastraflaw.apparel_core.api.item_link_query',
			filters: { variant_of: 'FB', _usage_fieldname: 'fabric', _attribute_name: 'Fabric' },
		}));
	},
});
