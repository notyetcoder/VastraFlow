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
	["fabric", "collar_type"].forEach((field) => {
		frm.set_query(field, () => ({ filters: filters[field] || {} }));
	});

	// The garment itself is picked in the standard Items table, not a separate
	// field - restrict item_code there to the Products group, but only while this
	// is a garment order, so an ordinary Sales Order keeps its normal item picker.
	frm.set_query("item_code", "items", () => {
		return frm.doc.is_garment_order ? { filters: filters.product_type || {} } : {};
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

// All three sleeve columns (Full/Half/Sleeveless) are always visible and editable.
//
// This used to hide the two columns that didn't match the selected Sleeve Type via
// grid.update_docfield_property(), which mutates Frappe's *shared* cached docfield
// definition for the whole child doctype - not something scoped to this one form.
// If that ran while the grid had no rows yet (e.g. a fresh form before the matrix
// populates), the hidden state could get stuck from a previous edit and never
// reset, leaving a column permanently non-interactive - which looked exactly like
// "the Size Matrix doesn't accept input." Always showing all three columns removes
// that whole failure mode. The server (_normalize_sleeves) still only counts
// whichever column matches Sleeve Type when computing the total - see that field's
// description on the form.
vastraflow.apply_sleeve_columns = function (frm) {};

// The garment is picked in the standard Items table (item_code stays editable,
// filtered to Products - see apply_link_filters). Qty and Rate are not the user's
// to set though - those come from the Size & Sleeve Matrix and the Price Matrix -
// so only those two columns are locked, and only while this is a garment order.
vastraflow.lock_items_grid = function (frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) return;

	const lock = !!frm.doc.is_garment_order;
	try {
		["qty", "rate"].forEach((column) => grid.update_docfield_property(column, "read_only", lock ? 1 : 0));
		frm.set_df_property(
			"items",
			"description",
			lock
				? __("Qty and Rate are set automatically from the Size Matrix and Price Matrix below.")
				: ""
		);
		grid.refresh();
	} catch (e) {
		console.warn("VastraFlow: could not lock the Items grid columns", e);
	}
};

// Standard ERPNext requires a Delivery Date on every Items row before it will even
// let the browser submit a save - it does this in the client, before our server-side
// before_validate (which does the same fill) ever gets a chance to run. So the fill
// has to happen here too, or the save is blocked before VastraFlow sees it.
vastraflow.sync_item_delivery_dates = function (frm) {
	if (!frm.doc.is_garment_order || !frm.doc.delivery_date) return;
	(frm.doc.items || []).forEach((row) => {
		if (!row.delivery_date) row.delivery_date = frm.doc.delivery_date;
	});
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

// The garment item lives in the Items table, not a field on the form, and the
// server only mirrors it onto `product_type` on save - so for a live preview
// before that save happens, read it straight from the Items table instead.
vastraflow.current_product_item = function (frm) {
	const row = (frm.doc.items || [])[0];
	return row ? row.item_code : null;
};

vastraflow.refresh_price = function (frm) {
	if (!frm.doc.is_garment_order) return;
	const productItem = vastraflow.current_product_item(frm);
	if (!(productItem && frm.doc.fabric && frm.doc.sublimation_type)) {
		frm.set_value("vf_matched_rate", 0);
		return;
	}

	frappe.call({
		method: "vastraflow.apparel_core.pricing.preview_price",
		args: {
			product_type: productItem,
			fabric: frm.doc.fabric,
			sublimation_type: frm.doc.sublimation_type,
		},
		callback: (r) => {
			const result = r.message || {};
			frm.set_value("vf_matched_rate", result.rate || 0);
			if (!result.found) {
				frm.dashboard.set_headline_alert(
					__("No Price Matrix entry matches {0} + {1} + {2}.", [
						productItem,
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
		vastraflow.lock_items_grid(frm);
		vastraflow.get_config().then((config) => {
			if (!config.enabled) return;
			vastraflow.apply_link_filters(frm, config);
			vastraflow.apply_sleeve_columns(frm);
			vastraflow.add_manufacturing_buttons(frm, config);
		});
	},

	// Belt-and-braces: this runs right before the browser's own mandatory-field
	// check, which is what actually blocks the save if an Items row is missing a
	// Delivery Date - by the time our server-side before_validate could fix it,
	// the request has already been refused client-side.
	before_save: function (frm) {
		vastraflow.sync_item_delivery_dates(frm);
	},

	is_garment_order: function (frm) {
		vastraflow.lock_items_grid(frm);
		vastraflow.sync_item_delivery_dates(frm);
		vastraflow.get_config().then((config) => {
			vastraflow.populate_size_matrix(frm, config);
			vastraflow.apply_sleeve_columns(frm);
			if (frm.doc.is_garment_order) vastraflow.refresh_price(frm);
		});
	},

	delivery_date: function (frm) {
		vastraflow.sync_item_delivery_dates(frm);
	},

	sleeve_type: function (frm) {
		vastraflow.apply_sleeve_columns(frm);
		vastraflow.recalculate_total(frm);
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

// The garment item itself changing (picked in the standard Items table) also
// needs a fresh price preview - it is the third leg of the price match, same as
// Fabric and Sublimation Type above.
frappe.ui.form.on("Sales Order Item", {
	item_code: (frm) => vastraflow.refresh_price(frm),
	items_add: (frm) => {
		vastraflow.sync_item_delivery_dates(frm);
		vastraflow.refresh_price(frm);
	},
	items_remove: (frm) => vastraflow.refresh_price(frm),
});
