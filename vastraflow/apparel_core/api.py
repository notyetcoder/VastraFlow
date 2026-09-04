"""Whitelisted endpoints used by the VastraFlow client scripts."""

import frappe

from vastraflow.apparel_core.logging_utils import get_logger
from vastraflow.apparel_core.settings import (
	get_item_query_filters,
	get_option_values,
	get_settings,
	get_size_labels,
	sync_select_options,
)


def _filters_to_dict(filters: list[list]) -> dict:
	"""[["Item","name","like","FB%"]] -> {"name": ["like", "FB%"]} for frm.set_query."""
	out = {}
	for entry in filters:
		if len(entry) == 4:
			_, fieldname, operator, value = entry
		elif len(entry) == 3:
			fieldname, operator, value = entry
		else:
			continue
		out[fieldname] = value if operator == "=" else [operator, value]
	return out


@frappe.whitelist()
def get_form_config():
	"""Single call that gives the Sales Order form everything it needs."""
	settings = get_settings()

	return {
		"enabled": bool(settings.enabled),
		"auto_populate_size_matrix": bool(settings.auto_populate_size_matrix),
		"auto_create_item_line": bool(settings.auto_create_item_line),
		"enable_auto_bom": bool(settings.enable_auto_bom),
		"plain_option_value": settings.plain_option_value or "Plain",
		"sizes": get_size_labels(settings),
		"filters": {
			"product_type": _filters_to_dict(get_item_query_filters("product", settings)),
			"fabric": _filters_to_dict(get_item_query_filters("fabric", settings)),
			"collar_type": _filters_to_dict(get_item_query_filters("collar", settings)),
		},
		"options": {
			"sublimation_type": get_option_values("sublimation_options", settings),
			"sleeve_type": get_option_values("sleeve_options", settings),
			"stitching_type": get_option_values("stitching_options", settings),
			"button_quantity": get_option_values("button_options", settings),
		},
	}


@frappe.whitelist()
def resync_options():
	"""Re-apply the configured dropdown lists. Exposed as a button in Settings."""
	frappe.only_for("System Manager")
	applied = sync_select_options()
	frappe.clear_cache()
	get_logger().info(f"Dropdown options re-synced: {list(applied)}")
	return applied


@frappe.whitelist()
def get_setup_status():
	"""Readiness checklist shown on the Settings General tab."""
	settings = get_settings()

	def count(doctype, filters=None):
		try:
			return frappe.db.count(doctype, filters or {})
		except Exception:
			return 0

	product_group = settings.product_item_group
	fabric_group = settings.fabric_item_group

	checks = [
		{
			"label": "Company created",
			"ok": count("Company") > 0,
			"hint": "ERPNext needs at least one Company.",
			"route": "/app/company",
		},
		{
			"label": f"Products in '{product_group}'",
			"ok": count("Item", {"item_group": product_group}) > 0 if product_group else False,
			"hint": "Add the garments you sell, e.g. POLO.",
			"route": "/app/item",
		},
		{
			"label": f"Fabrics in '{fabric_group}'",
			"ok": count("Item", {"item_group": fabric_group}) > 0 if fabric_group else False,
			"hint": "Add fabric items, e.g. FB-MICRO.",
			"route": "/app/item",
		},
		{
			"label": "Price Matrix entries submitted",
			"ok": count("VastraFlow Price Matrix", {"docstatus": 1}) > 0,
			"hint": "Submit at least one price row, or orders cannot be submitted.",
			"route": "/app/vastraflow-price-matrix",
		},
		{
			"label": "BOM Rule defined",
			"ok": count("VastraFlow BOM Rule", {"is_active": 1}) > 0,
			"hint": "Optional. Without one, the fallback recipe on the Manufacturing tab is used.",
			"route": "/app/vastraflow-bom-rule",
			"optional": True,
		},
	]

	return {
		"checks": checks,
		"ready": all(c["ok"] for c in checks if not c.get("optional")),
		"counts": {
			"garment_orders": count("Sales Order", {"is_garment_order": 1}),
			"auto_boms": count("BOM", {"vastraflow_auto_generated": 1}),
			"price_rows": count("VastraFlow Price Matrix", {"docstatus": 1}),
		},
	}


@frappe.whitelist()
def load_starter_data():
	"""Create a working demo set so a fresh install can be tried immediately."""
	frappe.only_for("System Manager")
	from vastraflow.apparel_core.demo_data import create_starter_data

	result = create_starter_data()
	frappe.db.commit()
	return result


# --- Blueprint-compatible endpoints ------------------------------------------


@frappe.whitelist()
def get_attribute_values(attribute_name: str):
	"""Values of an Item Attribute, in display order."""
	try:
		rows = frappe.get_all(
			"Item Attribute Value",
			filters={"parent": attribute_name},
			fields=["attribute_value"],
			order_by="idx",
		)
		return [r["attribute_value"] for r in rows]
	except Exception as exc:
		get_logger().error(f"Attribute lookup failed for {attribute_name}: {exc}")
		return []


@frappe.whitelist()
def check_product_type(product_type: str):
	if not product_type:
		return {"status": "error", "message": "No product type supplied"}
	if frappe.db.exists("Item", product_type):
		return {"status": "ok", "message": "Product type valid"}
	return {"status": "error", "message": f"Item {product_type} not found"}
