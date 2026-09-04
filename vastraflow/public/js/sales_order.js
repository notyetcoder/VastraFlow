// VastraFlow - Sales Order form behaviour.
//
// Everything here is inert unless "Is Garment Order" is ticked, so a normal Sales
// Order keeps its stock ERPNext behaviour.

frappe.provide("vastraflow");

vastraflow.SLEEVE_COLUMNS = {
	"Full Sleeve": "full_sleeve",
	"Half Sleeve": "half_sleeve",
	Sleeveless: "sleeveless",
};
vastraflow.ALL_SLEEVE_COLUMNS = ["full_sleeve", "half_sleeve", "sleeveless"];

// Config is per-session, not per-form-load.
vastraflow.get_config = function () {
	if (!vastraflow._config_promise) {
		vastraflow._config_promise = frappe
			.call({ method: "vastraflow.apparel_core.api.get_form_config" })
			.then((r) => r.message || {});
	}
	return vastraflow._config_promise;
};

vastraflow.apply_link_filters = function (frm, config) {
	const filters = (config && config.filters) || {};
	["product_type", "fabric", "collar_type"].forEach((field) => {
		frm.set_query(field, () => ({ filters: filters[field] || {} }));
	});
};

vastraflow.populate_size_matrix = function (frm, config) {
	if (!frm.doc.is_garment_order) return;
	if (!config.auto_populate_size_matrix) return;
	if ((frm.doc.size_matrix || []).length) return;

	(config.sizes || []).forEach((size) => {
		const row = frm.add_child("size_matrix");
		row.size = size;
		row.full_sleeve = 0;
		row.half_sleeve = 0;
		row.sleeveless = 0;
		row.row_total = 0;
	});
	frm.refresh_field("size_matrix");
};

// Show only the sleeve column that matches the selected sleeve type.
vastraflow.apply_sleeve_columns = function (frm) {
	const grid = frm.fields_dict.size_matrix && frm.fields_dict.size_matrix.grid;
	if (!grid) return;

	const keep = vastraflow.SLEEVE_COLUMNS[frm.doc.sleeve_type];
	try {
		vastraflow.ALL_SLEEVE_COLUMNS.forEach((column) => {
			const hidden = keep && column !== keep ? 1 : 0;
			grid.update_docfield_property(column, "hidden", hidden);
			grid.update_docfield_property(column, "in_list_view", hidden ? 0 : 1);
		});
		grid.refresh();
	} catch (e) {
		// A framework difference must never break the form.
		console.warn("VastraFlow: could not toggle sleeve columns", e);
	}
};

vastraflow.recalculate_total = function (frm) {
	let total = 0;
	(frm.doc.size_matrix || []).forEach((row) => {
		const row_total =
			(row.full_sleeve || 0) + (row.half_sleeve || 0) + (row.sleeveless || 0);
		row.row_total = row_total;
		total += row_total;
	});
	frm.set_value("garment_total_qty", total);
	frm.refresh_field("size_matrix");
};

vastraflow.refresh_price = function (frm) {
	if (!frm.doc.is_garment_order) return;
	if (!(frm.doc.product_type && frm.doc.fabric && frm.doc.sublimation_type)) {
		frm.set_value("vf_matched_rate", 0);
		return;
	}

	frappe.call({
		method: "vastraflow.apparel_core.pricing.preview_price",
		args: {
			product_type: frm.doc.product_type,
			fabric: frm.doc.fabric,
			sublimation_type: frm.doc.sublimation_type,
		},
		callback: (r) => {
			const result = r.message || {};
			frm.set_value("vf_matched_rate", result.rate || 0);
			if (!result.found) {
				frm.dashboard.set_headline_alert(
					__("No Price Matrix entry matches {0} + {1} + {2}.", [
						frm.doc.product_type,
						frm.doc.fabric,
						frm.doc.sublimation_type,
					]),
					"orange"
				);
			} else {
				frm.dashboard.clear_headline();
			}
		},
	});
};

vastraflow.add_manufacturing_buttons = function (frm, config) {
	if (!frm.doc.is_garment_order || frm.doc.docstatus !== 1) return;
	if (!config.enable_auto_bom) return;

	frm.add_custom_button(
		__("Preview BOM"),
		() => {
			frappe.call({
				method: "vastraflow.apparel_core.bom_engine.preview_bom",
				args: { sales_order: frm.doc.name },
				freeze: true,
				callback: (r) => {
					const data = r.message || {};
					const rows = (data.items || [])
						.map(
							(i) =>
								`<tr><td>${frappe.utils.escape_html(i.item_code)}</td>
								 <td style="text-align:right">${i.qty}</td>
								 <td>${frappe.utils.escape_html(i.uom || "")}</td></tr>`
						)
						.join("");

					frappe.msgprint({
						title: __("Generated BOM Preview"),
						indicator: "blue",
						message: `
							<p>${
								data.existing_bom
									? __("An existing BOM matches this specification: {0}", [
											`<a href="/app/bom/${data.existing_bom}"><b>${data.existing_bom}</b></a>`,
									  ])
									: __("A new BOM will be created for this specification.")
							}</p>
							<p><small>${__("Recipe")}: ${
								data.rule
									? `<a href="/app/vastraflow-bom-rule/${data.rule}">${data.rule}</a>`
									: __("fallback defaults from Settings")
						  } &middot; ${__("Reuse key")}: <code>${data.signature}</code></small></p>
							<table class="table table-bordered" style="margin-top:8px">
								<thead><tr><th>${__("Item")}</th><th style="text-align:right">${__(
							"Qty per Garment"
						)}</th><th>${__("UOM")}</th></tr></thead>
								<tbody>${rows || `<tr><td colspan="3">${__("No components resolved")}</td></tr>`}</tbody>
							</table>`,
					});
				},
			});
		},
		__("Manufacturing")
	);

	frm.add_custom_button(
		__("Create Work Order"),
		() => {
			frappe.confirm(
				__(
					"Create a Work Order for {0} pieces? The BOM will be generated automatically if one does not already exist.",
					[frm.doc.garment_total_qty]
				),
				() => {
					frappe.call({
						method: "vastraflow.apparel_core.bom_engine.create_work_order_for_sales_order",
						args: { sales_order: frm.doc.name },
						freeze: true,
						freeze_message: __("Generating BOM and Work Order..."),
						callback: (r) => {
							const name = (r.message || {}).work_order;
							if (name) {
								frappe.show_alert({
									message: __("Work Order {0} created", [name]),
									indicator: "green",
								});
								frappe.set_route("Form", "Work Order", name);
							}
						},
					});
				}
			);
		},
		__("Manufacturing")
	);
};

frappe.ui.form.on("Sales Order", {
	onload: function (frm) {
		vastraflow.get_config().then((config) => {
			vastraflow.apply_link_filters(frm, config);
		});
	},

	refresh: function (frm) {
		vastraflow.get_config().then((config) => {
			if (!config.enabled) return;
			vastraflow.apply_link_filters(frm, config);
			vastraflow.apply_sleeve_columns(frm);
			vastraflow.add_manufacturing_buttons(frm, config);
		});
	},

	is_garment_order: function (frm) {
		vastraflow.get_config().then((config) => {
			vastraflow.populate_size_matrix(frm, config);
			vastraflow.apply_sleeve_columns(frm);
			if (frm.doc.is_garment_order) vastraflow.refresh_price(frm);
		});
	},

	sleeve_type: function (frm) {
		vastraflow.apply_sleeve_columns(frm);
		vastraflow.recalculate_total(frm);
	},

	product_type: function (frm) {
		vastraflow.refresh_price(frm);
	},

	fabric: function (frm) {
		vastraflow.refresh_price(frm);
	},

	sublimation_type: function (frm) {
		vastraflow.refresh_price(frm);
	},
});

frappe.ui.form.on("Sales Order Size Matrix", {
	full_sleeve: (frm) => vastraflow.recalculate_total(frm),
	half_sleeve: (frm) => vastraflow.recalculate_total(frm),
	sleeveless: (frm) => vastraflow.recalculate_total(frm),
	size_matrix_remove: (frm) => vastraflow.recalculate_total(frm),
});
