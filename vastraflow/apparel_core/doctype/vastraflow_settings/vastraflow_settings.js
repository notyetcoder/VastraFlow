// VastraFlow Settings - setup checklist, starter data and activity view.

frappe.ui.form.on("VastraFlow Settings", {
	refresh: function (frm) {
		frm.add_custom_button(__("Load Starter Data"), () => load_starter_data(frm));
		frm.add_custom_button(__("Re-sync Dropdowns"), () => resync_options(frm));

		frm.add_custom_button(__("Price Matrix"), () =>
			frappe.set_route("List", "VastraFlow Price Matrix")
		);
		frm.add_custom_button(__("BOM Rules"), () => frappe.set_route("List", "VastraFlow BOM Rule"));

		render_setup_status(frm);
		render_activity(frm);
	},

	size_mode: function (frm) {
		frm.refresh_field("sizes");
	},
});

function render_setup_status(frm) {
	const wrapper = frm.get_field("setup_html").$wrapper;
	wrapper.html(`<div style="color:#6b7280">${__("Loading setup status...")}</div>`);

	frappe.call({
		method: "vastraflow.apparel_core.api.get_setup_status",
		callback: (r) => {
			const data = r.message || {};
			const checks = data.checks || [];
			const counts = data.counts || {};

			const rows = checks
				.map((c) => {
					const icon = c.ok ? "&#10003;" : c.optional ? "&#9675;" : "&#10007;";
					const color = c.ok ? "#16a34a" : c.optional ? "#9ca3af" : "#dc2626";
					const hint = c.ok
						? ""
						: `<div style="font-size:11px;color:#6b7280">${frappe.utils.escape_html(
								c.hint || ""
						  )}</div>`;
					return `<li style="margin-bottom:6px;list-style:none">
						<span style="color:${color};font-weight:700;margin-right:6px">${icon}</span>
						<a href="${c.route}" style="color:inherit">${frappe.utils.escape_html(c.label)}</a>
						${c.optional ? '<span style="font-size:11px;color:#9ca3af"> (optional)</span>' : ""}
						${hint}
					</li>`;
				})
				.join("");

			const banner = data.ready
				? `<div style="padding:8px 10px;background:#f0fdf4;border-left:3px solid #16a34a;border-radius:4px;margin-bottom:10px">
						<b>${__("Ready")}</b> &mdash; ${__("garment orders can be created and submitted.")}
				   </div>`
				: `<div style="padding:8px 10px;background:#fff7ed;border-left:3px solid #f59e0b;border-radius:4px;margin-bottom:10px">
						<b>${__("Setup incomplete")}</b> &mdash; ${__(
						"finish the unticked items below, or press Load Starter Data."
				  )}
				   </div>`;

			wrapper.html(`
				${banner}
				<ul style="padding-left:0;margin-bottom:12px">${rows}</ul>
				<div style="display:flex;gap:18px;font-size:12px;color:#374151;border-top:1px solid #e5e7eb;padding-top:10px">
					<div><b style="font-size:16px">${counts.garment_orders || 0}</b><br>${__("Garment orders")}</div>
					<div><b style="font-size:16px">${counts.price_rows || 0}</b><br>${__("Priced combinations")}</div>
					<div><b style="font-size:16px">${counts.auto_boms || 0}</b><br>${__("Auto-generated BOMs")}</div>
				</div>`);
		},
	});
}

function render_activity(frm) {
	const wrapper = frm.get_field("log_viewer_html").$wrapper;

	frappe.call({
		method: "vastraflow.apparel_core.logging_utils.get_recent_activity",
		args: { limit: 20 },
		callback: (r) => {
			const data = r.message || {};

			const table = (title, rows, columns) => {
				if (!rows || !rows.length) {
					return `<h5 style="margin-top:14px">${title}</h5><p style="color:#9ca3af">${__(
						"Nothing yet."
					)}</p>`;
				}
				const head = columns.map((c) => `<th>${c.label}</th>`).join("");
				const body = rows
					.map(
						(row) =>
							`<tr>${columns
								.map((c) => {
									let value = row[c.field];
									if (c.field === "creation" || c.field === "modified") {
										value = frappe.datetime.str_to_user(value);
									}
									const text = frappe.utils.escape_html(String(value == null ? "" : value));
									return `<td>${
										c.link ? `<a href="${c.link}${row.name}">${text}</a>` : text
									}</td>`;
								})
								.join("")}</tr>`
					)
					.join("");
				return `<h5 style="margin-top:14px">${title}</h5>
					<table class="table table-bordered" style="font-size:12px">
						<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
			};

			wrapper.html(`
				${table(__("Recent garment orders"), data.orders, [
					{ label: __("Order"), field: "name", link: "/app/sales-order/" },
					{ label: __("Product"), field: "product_type" },
					{ label: __("Pieces"), field: "garment_total_qty" },
					{ label: __("Status"), field: "status" },
					{ label: __("Updated"), field: "modified" },
				])}
				${table(__("Auto-generated BOMs"), data.boms, [
					{ label: __("BOM"), field: "name", link: "/app/bom/" },
					{ label: __("Item"), field: "item" },
					{ label: __("Created"), field: "creation" },
				])}
				${table(__("Errors"), data.errors, [
					{ label: __("Reference"), field: "name", link: "/app/error-log/" },
					{ label: __("Method"), field: "title" },
					{ label: __("When"), field: "creation" },
				])}`);
		},
	});
}

function load_starter_data(frm) {
	frappe.confirm(
		__(
			"Create sample garments, fabrics, collars, trims, price rows and BOM rules? Existing records are left untouched."
		),
		() => {
			frappe.call({
				method: "vastraflow.apparel_core.api.load_starter_data",
				freeze: true,
				freeze_message: __("Creating starter data..."),
				callback: (r) => {
					const created = r.message || {};
					frappe.msgprint({
						title: __("Starter Data Ready"),
						indicator: "green",
						message: __("Created or verified {0} items, {1} price rows and {2} BOM rules.", [
							(created.items || []).length,
							(created.prices || []).length,
							(created.rules || []).length,
						]),
					});
					frm.reload_doc();
				},
			});
		}
	);
}

function resync_options(frm) {
	frappe.call({
		method: "vastraflow.apparel_core.api.resync_options",
		freeze: true,
		callback: () => {
			frappe.show_alert({ message: __("Dropdowns updated"), indicator: "green" });
		},
	});
}
