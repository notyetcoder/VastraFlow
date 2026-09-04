"""Central access to VastraFlow Settings.

Everything the blueprint hardcoded - sizes, dropdown options, item filters - is read
from the singleton here, so the app is configured from the Settings page rather than
from code.
"""

import frappe

SETTINGS_DOCTYPE = "VastraFlow Settings"

# Settings table field -> the Sales Order field whose Select options it drives.
# `optional` prepends a blank line so the user can clear the field.
OPTION_SOURCES = {
	"sublimation_options": {"fieldname": "sublimation_type", "optional": False},
	"sleeve_options": {"fieldname": "sleeve_type", "optional": False},
	"stitching_options": {"fieldname": "stitching_type", "optional": True},
	"button_options": {"fieldname": "button_quantity", "optional": True},
}

# Hard ceiling so a fat-fingered size range cannot generate thousands of grid rows.
MAX_SIZE_ROWS = 200


def get_settings():
	"""Return the settings singleton. Safe to call before the record exists."""
	return frappe.get_cached_doc(SETTINGS_DOCTYPE)


def is_enabled() -> bool:
	try:
		return bool(get_settings().enabled)
	except Exception:
		return False


def get_option_values(fieldname_or_table: str, settings=None) -> list[str]:
	"""Values of one option table, e.g. get_option_values("sublimation_options")."""
	settings = settings or get_settings()
	rows = settings.get(fieldname_or_table) or []
	return [(r.option_value or "").strip() for r in rows if (r.option_value or "").strip()]


def get_size_labels(settings=None) -> list[str]:
	"""Size labels for the matrix grid, from either the numeric range or the custom list."""
	settings = settings or get_settings()

	if settings.size_mode == "Custom List":
		return [
			(r.size_label or "").strip()
			for r in (settings.sizes or [])
			if r.is_active and (r.size_label or "").strip()
		][:MAX_SIZE_ROWS]

	start = int(settings.size_start or 22)
	end = int(settings.size_end or 54)
	step = int(settings.size_step or 2)

	if step <= 0:
		step = 1
	if end < start:
		start, end = end, start

	labels = [str(s) for s in range(start, end + 1, step)]
	return labels[:MAX_SIZE_ROWS]


def get_size_factor(size_label: str, settings=None) -> float:
	"""Fabric multiplier configured for a size in Custom List mode. Defaults to 1."""
	settings = settings or get_settings()
	if settings.size_mode != "Custom List":
		return 1.0
	for row in settings.sizes or []:
		if (row.size_label or "").strip() == str(size_label).strip():
			return float(row.fabric_factor or 1) or 1.0
	return 1.0


def get_item_query_filters(kind: str, settings=None) -> list[list]:
	"""Link-field filters for product / fabric / collar, built from Settings."""
	settings = settings or get_settings()
	filters: list[list] = []

	group_field, prefix_field = {
		"product": ("product_item_group", "product_code_prefix"),
		"fabric": ("fabric_item_group", "fabric_code_prefix"),
		"collar": ("collar_item_group", "collar_code_prefix"),
	}.get(kind, (None, None))

	if not group_field:
		return filters

	group = (settings.get(group_field) or "").strip()
	prefix = (settings.get(prefix_field) or "").strip()

	if group:
		filters.append(["Item", "item_group", "=", group])
	if prefix:
		filters.append(["Item", "name", "like", f"{prefix}%"])

	# Never offer disabled items for selection.
	filters.append(["Item", "disabled", "=", 0])
	return filters


def sync_select_options(settings=None) -> dict:
	"""Push the configured option lists onto the Sales Order and Price Matrix fields.

	Called after the Settings singleton is saved, so editing a list in the UI updates
	the dropdowns immediately without a code change or migration.
	"""
	from vastraflow.apparel_core.custom_fields import set_custom_field_options

	settings = settings or get_settings()
	applied = {}

	for table_field, spec in OPTION_SOURCES.items():
		values = get_option_values(table_field, settings)
		if not values:
			continue

		options = "\n".join(values)
		if spec["optional"]:
			options = "\n" + options

		set_custom_field_options("Sales Order", spec["fieldname"], options)
		applied[spec["fieldname"]] = values

	# The Price Matrix sublimation field is a real DocType field, so it needs a
	# Property Setter rather than a Custom Field update.
	sublimation = get_option_values("sublimation_options", settings)
	if sublimation:
		frappe.make_property_setter(
			{
				"doctype": "VastraFlow Price Matrix",
				"fieldname": "sublimation_type",
				"property": "options",
				"value": "\n".join(sublimation),
				"property_type": "Text",
			},
			is_system_generated=True,
		)

	frappe.clear_cache(doctype="Sales Order")
	frappe.clear_cache(doctype="VastraFlow Price Matrix")
	return applied
