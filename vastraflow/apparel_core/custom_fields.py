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
DEFAULT_SUBLIMATION = "None\nFront Sublimation\nBack Sublimation\nFront & Back sublimation\nFull sublimation"
DEFAULT_SLEEVE = "Full Sleeve\nHalf Sleeve\nSleeveless\nMulti"
DEFAULT_STITCHING = "\nSingle Stitching\nDouble Stitching"
DEFAULT_BUTTON = "\nNone\nOne\nTwo"
DEFAULT_TREATMENT = "\nColour\nA4"
DEFAULT_COLOUR = "\nRed\nGreen\nBlue\nBlack\nWhite"

GARMENT = "eval:doc.is_garment_order"

# A sublimation panel (front/back) is "locked" - implied by the main Sublimation Type
# - for these combinations, and only needs its own Colour/A4 choice when it is NOT
# locked. Front & Back locks both, leaving only sleeve open on its own.
FRONT_LOCKED = "['Front Sublimation', 'Front & Back sublimation', 'Full sublimation']"
BACK_LOCKED = "['Back Sublimation', 'Front & Back sublimation', 'Full sublimation']"
ANY_SUBLIMATION = "['Front Sublimation', 'Back Sublimation', 'Front & Back sublimation', 'Full sublimation']"

# Front/Back/Sleeve stay visible at all times now (never hidden) - only *blocked
# from editing* via read_only_depends_on when locked. Showing a greyed-out field
# communicates "this doesn't apply right now" far better than making it vanish,
# which repeatedly looked like a bug in earlier rounds ("why is Front missing").
# These are the read-only conditions - the *negation* of "this panel is open".
# "None" is a non-empty string, so a plain `doc.sublimation_type &&` truthiness
# check would get this backwards - membership in ANY_SUBLIMATION is what matters.
FRONT_LOCKED_RO = f"eval:{FRONT_LOCKED}.includes(doc.sublimation_type) || !{ANY_SUBLIMATION}.includes(doc.sublimation_type)"
BACK_LOCKED_RO = f"eval:{BACK_LOCKED}.includes(doc.sublimation_type) || !{ANY_SUBLIMATION}.includes(doc.sublimation_type)"
SLEEVE_LOCKED_RO = f"eval:doc.sleeve_type=='Sleeveless' || !{ANY_SUBLIMATION}.includes(doc.sublimation_type)"


def get_custom_fields() -> dict:
	return {
		"Sales Order": [
			{
				"fieldname": "vf_garment_section",
				"label": "GarmentOS - Garment Specification",
				"fieldtype": "Section Break",
				# Below the standard Items table (like every other Sales Order detail
				# section) - not before it. An earlier attempt anchored this to
				# "customer", which collided with ERPNext's own "customer_name" field
				# (both insert_after "customer") and broke the Customer section's
				# layout. Never anchor a section to the same field ERPNext itself
				# already chains a field onto.
				"insert_after": "total_qty",
				"collapsible": 0,
				"description": "The garment itself is picked in the Items table above, filtered to Products once Is Garment Order is ticked.",
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
				# Not a user input. Auto-synced in before_validate from the first row of
				# the standard Items table - the user picks the garment there, the normal
				# ERPNext way, instead of a second redundant field. Kept as a real
				# (hidden) field rather than deleted because pricing, the BOM engine, the
				# report and the print format all key off it - this way none of them
				# need to change, they just keep reading a field that now populates
				# itself instead of being typed twice.
				"fieldname": "product_type",
				"label": "Product Type",
				"fieldtype": "Link",
				"options": "Item",
				"insert_after": "is_garment_order",
				"hidden": 1,
				"read_only": 1,
				"no_copy": 1,
				# Explicitly blanked, not omitted: an earlier version of this field had
				# depends_on/mandatory_depends_on set, and create_custom_fields(update=True)
				# only *sets* keys present in this dict - it never clears a key that is
				# simply absent. Leaving these out reintroduces the exact "Product Type
				# is required" bug this fixed.
				"depends_on": "",
				"mandatory_depends_on": "",
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
				"description": "A reference photo prints on the Job Card - change the Item's own image to replace it. Colour is set below, in Sublimation Panels.",
			},
			{
				"fieldname": "vf_spec_row2",
				"label": "",
				"fieldtype": "Section Break",
				"insert_after": "collar_type",
				"depends_on": GARMENT,
			},
			{
				"fieldname": "stitching_type",
				"label": "Stitching Type",
				"fieldtype": "Select",
				"options": DEFAULT_STITCHING,
				"insert_after": "vf_spec_row2",
				"depends_on": GARMENT,
			},
			{
				"fieldname": "vf_spec_column1",
				"fieldtype": "Column Break",
				"insert_after": "stitching_type",
			},
			{
				"fieldname": "button_quantity",
				"label": "Button Quantity",
				"fieldtype": "Select",
				"options": DEFAULT_BUTTON,
				"insert_after": "vf_spec_column1",
				"depends_on": GARMENT,
			},
			{
				"fieldname": "vf_spec_column2",
				"fieldtype": "Column Break",
				"insert_after": "button_quantity",
			},
			{
				"fieldname": "sleeve_type",
				"label": "Sleeve Type",
				"fieldtype": "Select",
				"options": DEFAULT_SLEEVE,
				"insert_after": "vf_spec_column2",
				"depends_on": GARMENT,
				"mandatory_depends_on": GARMENT,
				"description": "Full/Half/Sleeveless keeps only that column of the Size Matrix. Multi counts all three, for an order mixing sleeve types.",
			},
			{
				"fieldname": "vf_panel_section",
				"label": "Sublimation Panels",
				"fieldtype": "Section Break",
				"insert_after": "sleeve_type",
				"depends_on": GARMENT,
				"description": (
					"All six options always show - Front/Back/Sleeve grey out (blocked, not "
					"hidden) when the main Sublimation Type already covers them. Full "
					"sublimation blocks all three; Front/Back/Front & Back sublimation block "
					"just that panel. Border and Collar Colour are always free to set. None of "
					"this affects pricing or the BOM - the Colour/A4 options are editable any "
					"time on the Dropdown Options tab of VastraFlow Settings."
				),
			},
			{
				"fieldname": "sublimation_type",
				"label": "Sublimation Type",
				"fieldtype": "Select",
				"options": DEFAULT_SUBLIMATION,
				"insert_after": "vf_panel_section",
				"depends_on": GARMENT,
				"mandatory_depends_on": GARMENT,
			},
			{
				"fieldname": "vf_panel_column1",
				"fieldtype": "Column Break",
				"insert_after": "sublimation_type",
			},
			{
				"fieldname": "front_treatment",
				"label": "Front",
				"fieldtype": "Select",
				"options": DEFAULT_TREATMENT,
				"insert_after": "vf_panel_column1",
				"depends_on": GARMENT,
				"read_only_depends_on": FRONT_LOCKED_RO,
				"description": "Blocked when Sublimation Type already covers the front.",
			},
			{
				# A Column Break here (instead of stacking the colour picker directly
				# below its treatment field) puts the two side by side - so choosing
				# "Colour" for Front expands rightward into its own column, rather than
				# pushing everything below it down the page.
				"fieldname": "vf_front_colour_column",
				"fieldtype": "Column Break",
				"insert_after": "front_treatment",
			},
			{
				"fieldname": "front_colour",
				"label": "Front Colour",
				"fieldtype": "Select",
				"options": DEFAULT_COLOUR,
				"insert_after": "vf_front_colour_column",
				"depends_on": "eval:doc.front_treatment=='Colour'",
				"mandatory_depends_on": "",  # print-only field, never blocks a save
			},
			{
				"fieldname": "vf_panel_column2",
				"fieldtype": "Column Break",
				"insert_after": "front_colour",
			},
			{
				"fieldname": "back_treatment",
				"label": "Back",
				"fieldtype": "Select",
				"options": DEFAULT_TREATMENT,
				"insert_after": "vf_panel_column2",
				"depends_on": GARMENT,
				"read_only_depends_on": BACK_LOCKED_RO,
				"description": "Blocked when Sublimation Type already covers the back.",
			},
			{
				"fieldname": "vf_back_colour_column",
				"fieldtype": "Column Break",
				"insert_after": "back_treatment",
			},
			{
				"fieldname": "back_colour",
				"label": "Back Colour",
				"fieldtype": "Select",
				"options": DEFAULT_COLOUR,
				"insert_after": "vf_back_colour_column",
				"depends_on": "eval:doc.back_treatment=='Colour'",
				"mandatory_depends_on": "",  # print-only field, never blocks a save
			},
			{
				# A genuine new row (Section Break) is safe here, unlike the earlier
				# design: every field in this row is now always visible (read-only when
				# locked, never hidden), so nothing can be left stranded alone the way
				# Border used to be on a Sleeveless order.
				"fieldname": "vf_panel_row2",
				"label": "",
				"fieldtype": "Section Break",
				"insert_after": "back_colour",
				"depends_on": GARMENT,
			},
			{
				"fieldname": "sleeve_treatment",
				"label": "Sleeve",
				"fieldtype": "Select",
				"options": DEFAULT_TREATMENT,
				"insert_after": "vf_panel_row2",
				"depends_on": GARMENT,
				"read_only_depends_on": SLEEVE_LOCKED_RO,
				"description": "Blocked when Sleeve Type is Sleeveless, or Sublimation Type already covers it.",
			},
			{
				"fieldname": "vf_sleeve_colour_column",
				"fieldtype": "Column Break",
				"insert_after": "sleeve_treatment",
			},
			{
				"fieldname": "sleeve_colour",
				"label": "Sleeve Colour",
				"fieldtype": "Select",
				"options": DEFAULT_COLOUR,
				"insert_after": "vf_sleeve_colour_column",
				"depends_on": "eval:doc.sleeve_treatment=='Colour'",
				"mandatory_depends_on": "",  # print-only field, never blocks a save
			},
			{
				"fieldname": "vf_panel_column3",
				"fieldtype": "Column Break",
				"insert_after": "sleeve_colour",
			},
			{
				# No treatment choice, unlike Front/Back/Sleeve - the border is a trim
				# colour, not a print panel, so "A4 transfer" makes no sense for it.
				# Always free to set, never locked.
				"fieldname": "border_colour",
				"label": "Border Colour",
				"fieldtype": "Select",
				"options": DEFAULT_COLOUR,
				"insert_after": "vf_panel_column3",
				"depends_on": GARMENT,
				"description": "Optional. Print-only.",
			},
			{
				"fieldname": "vf_panel_column4",
				"fieldtype": "Column Break",
				"insert_after": "border_colour",
			},
			{
				# Same reasoning as Border Colour - a direct colour, no treatment step.
				"fieldname": "collar_colour",
				"label": "Collar Colour",
				"fieldtype": "Select",
				"options": DEFAULT_COLOUR,
				"insert_after": "vf_panel_column4",
				"depends_on": GARMENT,
				"description": "Optional. Print-only.",
			},
			{
				"fieldname": "vf_artwork_section",
				"label": "Artwork",
				"fieldtype": "Section Break",
				"insert_after": "collar_colour",
				"depends_on": GARMENT,
				"collapsible": 1,
			},
			{
				"fieldname": "artwork_file",
				"label": "Artwork File",
				"fieldtype": "Attach Image",
				"insert_after": "vf_artwork_section",
				"description": "Recommended for any sublimation other than None. Shows as a thumbnail once attached.",
			},
			{
				"fieldname": "vf_artwork_column",
				"fieldtype": "Column Break",
				"insert_after": "artwork_file",
			},
			{
				"fieldname": "logo_file",
				"label": "Logo File",
				"fieldtype": "Attach Image",
				"insert_after": "vf_artwork_column",
				"description": "Optional. Printed on the Production Job Card. Shows as a thumbnail once attached.",
			},
			{
				"fieldname": "team_name",
				"label": "Team Name",
				"fieldtype": "Data",
				"insert_after": "logo_file",
				"depends_on": GARMENT,
				"description": "Optional. Printed on the Job Card only when filled in.",
			},
			{
				"fieldname": "vf_notes",
				"label": "Notes",
				"fieldtype": "Small Text",
				"insert_after": "team_name",
				"depends_on": GARMENT,
				"description": "Optional. Printed on the Job Card only when filled in.",
			},
			{
				"fieldname": "vf_size_matrix_section",
				"label": "Size & Sleeve Matrix",
				"fieldtype": "Section Break",
				"insert_after": "vf_notes",
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
