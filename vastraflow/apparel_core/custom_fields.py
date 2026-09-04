"""Custom fields VastraFlow adds to standard doctypes.

Defined in code rather than as fixtures so that installing the app is a single
command and re-running it is always safe.

Design rule: every garment field is gated behind `is_garment_order`. A Sales Order
without that flag behaves exactly like stock ERPNext - no extra mandatory fields,
no extra validation. This is what keeps VastraFlow from breaking ordinary selling.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Seed values only. Once VastraFlow Settings is saved these are replaced by whatever
# the user configured on the Dropdown Options tab.
DEFAULT_SUBLIMATION = "Plain\nFront Sublimation\nBack Sublimation\nFront & Back sublimation\nFull sublimation"
DEFAULT_SLEEVE = "Full Sleeve\nHalf Sleeve\nSleeveless"
DEFAULT_STITCHING = "\nSingle Stitching\nDouble Stitching"
DEFAULT_BUTTON = "\nNone\nOne\nTwo"

GARMENT = "eval:doc.is_garment_order"


def get_custom_fields() -> dict:
	return {
		"Sales Order": [
			{
				"fieldname": "vf_garment_section",
				"label": "GarmentOS - Garment Specification",
				"fieldtype": "Section Break",
				"insert_after": "total_qty",
				"collapsible": 0,
			},
			{
				"fieldname": "is_garment_order",
				"label": "Is Garment Order",
				"fieldtype": "Check",
				"insert_after": "vf_garment_section",
				"description": "Turn on to capture garment specifications and use VastraFlow pricing and BOM automation.",
				"in_standard_filter": 1,
			},
			{
				"fieldname": "product_type",
				"label": "Product Type",
				"fieldtype": "Link",
				"options": "Item",
				"insert_after": "is_garment_order",
				"depends_on": GARMENT,
				"mandatory_depends_on": GARMENT,
				"description": "Finished garment, e.g. Polo, T-Shirt",
			},
			{
				"fieldname": "fabric",
				"label": "Fabric",
				"fieldtype": "Link",
				"options": "Item",
				"insert_after": "product_type",
				"depends_on": GARMENT,
				"mandatory_depends_on": GARMENT,
			},
			{
				"fieldname": "collar_type",
				"label": "Collar Type",
				"fieldtype": "Link",
				"options": "Item",
				"insert_after": "fabric",
				"depends_on": GARMENT,
			},
			{
				"fieldname": "vf_spec_column",
				"fieldtype": "Column Break",
				"insert_after": "collar_type",
			},
			{
				"fieldname": "sublimation_type",
				"label": "Sublimation Type",
				"fieldtype": "Select",
				"options": DEFAULT_SUBLIMATION,
				"insert_after": "vf_spec_column",
				"depends_on": GARMENT,
				"mandatory_depends_on": GARMENT,
			},
			{
				"fieldname": "sleeve_type",
				"label": "Sleeve Type",
				"fieldtype": "Select",
				"options": DEFAULT_SLEEVE,
				"insert_after": "sublimation_type",
				"depends_on": GARMENT,
				"mandatory_depends_on": GARMENT,
				"description": "Controls which columns of the size matrix are used",
			},
			{
				"fieldname": "stitching_type",
				"label": "Stitching Type",
				"fieldtype": "Select",
				"options": DEFAULT_STITCHING,
				"insert_after": "sleeve_type",
				"depends_on": GARMENT,
			},
			{
				"fieldname": "button_quantity",
				"label": "Button Quantity",
				"fieldtype": "Select",
				"options": DEFAULT_BUTTON,
				"insert_after": "stitching_type",
				"depends_on": GARMENT,
			},
			{
				"fieldname": "vf_artwork_section",
				"label": "Artwork",
				"fieldtype": "Section Break",
				"insert_after": "button_quantity",
				"depends_on": GARMENT,
				"collapsible": 1,
			},
			{
				"fieldname": "artwork_file",
				"label": "Artwork File",
				"fieldtype": "Attach",
				"insert_after": "vf_artwork_section",
				"description": "Sublimation artwork. Recommended for any non-plain sublimation.",
			},
			{
				"fieldname": "vf_artwork_column",
				"fieldtype": "Column Break",
				"insert_after": "artwork_file",
			},
			{
				"fieldname": "logo_file",
				"label": "Logo File",
				"fieldtype": "Attach",
				"insert_after": "vf_artwork_column",
				"description": "Printed on the Production Job Card",
			},
			{
				"fieldname": "vf_size_matrix_section",
				"label": "Size & Sleeve Matrix",
				"fieldtype": "Section Break",
				"insert_after": "logo_file",
				"depends_on": GARMENT,
			},
			{
				"fieldname": "size_matrix",
				"label": "Size Matrix",
				"fieldtype": "Table",
				"options": "Sales Order Size Matrix",
				"insert_after": "vf_size_matrix_section",
				"depends_on": GARMENT,
				"description": "Quantities per size. Only the column matching the selected sleeve type is counted.",
			},
			{
				"fieldname": "vf_totals_section",
				"fieldtype": "Section Break",
				"insert_after": "size_matrix",
				"depends_on": GARMENT,
			},
			{
				"fieldname": "garment_total_qty",
				"label": "Total Pieces",
				"fieldtype": "Int",
				"insert_after": "vf_totals_section",
				"read_only": 1,
				"depends_on": GARMENT,
				"bold": 1,
			},
			{
				"fieldname": "vf_totals_column",
				"fieldtype": "Column Break",
				"insert_after": "garment_total_qty",
			},
			{
				"fieldname": "vf_matched_rate",
				"label": "Matched Rate",
				"fieldtype": "Currency",
				"insert_after": "vf_totals_column",
				"read_only": 1,
				"depends_on": GARMENT,
				"description": "Rate found in the VastraFlow Price Matrix",
			},
			{
				"fieldname": "garmentos_generated",
				"label": "GarmentOS Generated",
				"fieldtype": "Check",
				"insert_after": "vf_matched_rate",
				"hidden": 1,
				"read_only": 1,
				"print_hide": 1,
				"no_copy": 1,
			},
			{
				"fieldname": "garmentos_price_status",
				"label": "Price Status",
				"fieldtype": "Select",
				"options": "\nPending\nMissing Price\nPriced",
				"insert_after": "garmentos_generated",
				"hidden": 1,
				"read_only": 1,
				"print_hide": 1,
				"no_copy": 1,
			},
		],
		# Marks the order line VastraFlow maintains from the size matrix, so it is
		# updated in place instead of duplicated, and manual lines are left alone.
		"Sales Order Item": [
			{
				"fieldname": "vf_generated",
				"label": "Built by VastraFlow",
				"fieldtype": "Check",
				"insert_after": "item_code",
				"read_only": 1,
				"hidden": 1,
				"print_hide": 1,
				"no_copy": 1,
			},
		],
		# Lets the BOM engine recognise and reuse the BOMs it generated.
		"BOM": [
			{
				"fieldname": "vastraflow_signature",
				"label": "VastraFlow Signature",
				"fieldtype": "Data",
				"insert_after": "item_name",
				"read_only": 1,
				"hidden": 1,
				"print_hide": 1,
				"no_copy": 1,
				"search_index": 1,
			},
			{
				"fieldname": "vastraflow_auto_generated",
				"label": "Generated by VastraFlow",
				"fieldtype": "Check",
				"insert_after": "vastraflow_signature",
				"read_only": 1,
				"print_hide": 1,
				"no_copy": 1,
			},
		],
	}


def create_all():
	create_custom_fields(get_custom_fields(), update=True)


def set_custom_field_options(doctype: str, fieldname: str, options: str) -> bool:
	"""Update the Select options of one custom field in place."""
	name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
	if not name:
		return False
	frappe.db.set_value("Custom Field", name, "options", options)
	return True
