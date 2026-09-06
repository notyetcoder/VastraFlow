"""VastraFlow's starter catalog.

Not generic demo data - this is the user's own catalog (Item.csv / Item Attribute.csv),
embedded as code so a fresh `bench install-app vastraflow` produces a ready-to-use
site with no separate import step. Triggered automatically from `install.after_install`
(wrapped so a failure there never blocks installation) and repeatable any time from
the "Load Starter Data" button on VastraFlow Settings - everything here is idempotent.

Item modelling: FB (fabric) and COLL (collar) are template Items with real Item
Variants, matching the source catalog exactly - variants are picked in the Fabric /
Collar Type fields via `variant_of`, not by item group or code prefix. Finished
garments (Track, T-Shirt, Shorts, Hoodie) and trims are flat Items, matching the
source catalog: none of them are variant-based there.
"""

import frappe

from vastraflow.apparel_core.logging_utils import get_logger

# --- Item Attributes (only the two used to build real Item Variants here; the
# rest - Sleeve, stitching, Sublimation, Colour, Button Count, Sizes - are already
# expected to exist from the user's own Item Attribute import, and VastraFlow reads
# its own dropdown lists from Settings rather than from these regardless). ---------
ATTRIBUTES = {
	"Fabric": [
		("Micro", "MI"),
		("Soft Micro", "S/M"),
		("Dotnet", "DN"),
		("Reebok Net", "R/N"),
		("Football Net", "F/N"),
		("Comboline", "CM"),
		("Polo Net", "PN"),
	],
	"Collar Type": [
		("Round Neck", "RN"),
		("V Neck", "VNE"),
		("Chinese", "CN"),
		("V Neck + Chinese", "VNCN"),
		("V Neck + Collar", "VNCO"),
		("Collar + Flanket", "COF"),
		("Chinese + Flanket", "CHF"),
		("Chinese + ZIP", "CHZ"),
		("Collar + ZIP", "CZ"),
	],
}

# code -> (attribute value, reference sketch filename)
FABRIC_VARIANTS = {
	"FB-MI": ("Micro", None),
	"FB-S/M": ("Soft Micro", None),
	"FB-DN": ("Dotnet", None),
	"FB-R/N": ("Reebok Net", None),
	"FB-F/N": ("Football Net", None),
	"FB-CM": ("Comboline", None),
	"FB-PN": ("Polo Net", None),
}
# Real product photos (Krishna Sports, 2026-08-14) for every variant except
# Collar + ZIP, which the user photographed and attached separately by hand -
# collar_zip.svg (a generated sketch) is only the fallback there until a matching
# photo exists.
COLLAR_VARIANTS = {
	"COLL-RN": ("Round Neck", "round_neck.jpg"),
	"COLL-VNE": ("V Neck", "v_neck.jpg"),
	"COLL-CN": ("Chinese", "chinese.jpg"),
	"COLL-VNCN": ("V Neck + Chinese", "v_neck_chinese.jpg"),
	"COLL-VNCO": ("V Neck + Collar", "v_neck_collar.jpg"),
	"COLL-COF": ("Collar + Flanket", "collar_flanket.jpg"),
	"COLL-CHF": ("Chinese + Flanket", "chinese_flanket.jpg"),
	"COLL-CHZ": ("Chinese + ZIP", "chinese_zip.jpg"),
	"COLL-CZ": ("Collar + ZIP", "collar_zip.svg"),
}

PRODUCTS = [
	("TR", "Track"),
	("TS", "T-Shirt"),
	("SH", "Shorts"),
	("HOO", "Hoodie"),
]
# Trims: (code, name, uom). UOM matches the source catalog (all "Nos"), even where a
# fractional UOM like Meter would suit thread better - that is the user's own item
# master to adjust, not ours to silently override.
TRIMS = [
	("ST", "Sewing Thread", "Nos"),
	("PB", "Poly Bag", "Nos"),
	("LAB", "Label", "Nos"),
	("BU", "Button", "Nos"),
]

# The user's real wholesale price list (Krishna Sports / P3, WhatsApp image
# 2026-08-08) for T-Shirt: Fabric x Sublimation -> rate. "Plain" and "Two Side
# Sublimation" in the source list are this app's "None" and "Front & Back
# sublimation". Only the four sublimation types actually priced there are seeded -
# "Back Sublimation" alone isn't in the source list, so no row is created for it.
TS_PRICE_LIST = {
	"FB-MI": {"None": 150, "Front Sublimation": 200, "Front & Back sublimation": 250, "Full sublimation": 310},
	"FB-S/M": {"None": 160, "Front Sublimation": 210, "Front & Back sublimation": 260, "Full sublimation": 320},
	"FB-DN": {"None": 170, "Front Sublimation": 220, "Front & Back sublimation": 270, "Full sublimation": 330},
	"FB-R/N": {"None": 175, "Front Sublimation": 225, "Front & Back sublimation": 275, "Full sublimation": 335},
	"FB-F/N": {"None": 180, "Front Sublimation": 230, "Front & Back sublimation": 280, "Full sublimation": 340},
	"FB-CM": {"None": 210, "Front Sublimation": 260, "Front & Back sublimation": 310, "Full sublimation": 370},
	"FB-PN": {"None": 240, "Front Sublimation": 290, "Front & Back sublimation": 340, "Full sublimation": 400},
}
PRICES = [
	("TS", fabric, sublimation, rate)
	for fabric, by_sublimation in TS_PRICE_LIST.items()
	for sublimation, rate in by_sublimation.items()
] + [
	("TR", "FB-MI", "None", 220),
	("SH", "FB-DN", "None", 160),
	("HOO", "FB-CM", "Full sublimation", 420),
]


def _ensure_root_item_group():
	"""ERPNext's own setup wizard normally creates this root group - but a fresh
	site that installs this app before running that wizard has no Item Group at
	all yet, and every other Item Group is created as a child of this one. Found
	missing on a genuinely fresh site (no Company, wizard never run) - a real gap,
	not a hypothetical one."""
	if not frappe.db.exists("Item Group", "All Item Groups"):
		doc = frappe.new_doc("Item Group")
		doc.item_group_name = "All Item Groups"
		doc.is_group = 1
		doc.flags.ignore_permissions = True
		doc.insert()


def _ensure_item_group(name: str, parent: str = "All Item Groups"):
	if frappe.db.exists("Item Group", name):
		return name
	_ensure_root_item_group()
	doc = frappe.new_doc("Item Group")
	doc.item_group_name = name
	doc.parent_item_group = parent
	doc.is_group = 0
	doc.flags.ignore_permissions = True
	doc.insert()
	return name


def _ensure_uom(name: str):
	if not frappe.db.exists("UOM", name):
		doc = frappe.new_doc("UOM")
		doc.uom_name = name
		doc.flags.ignore_permissions = True
		doc.insert()
	return name


def _ensure_item_attribute(name: str, values: list[tuple[str, str]]):
	if frappe.db.exists("Item Attribute", name):
		return name
	doc = frappe.new_doc("Item Attribute")
	doc.attribute_name = name
	for value, abbr in values:
		doc.append("item_attribute_values", {"attribute_value": value, "abbr": abbr})
	doc.flags.ignore_permissions = True
	doc.insert()
	return name


def _ensure_template_item(code: str, name: str, group: str, uom: str, attribute: str):
	if frappe.db.exists("Item", code):
		return code
	item = frappe.new_doc("Item")
	item.item_code = code
	item.item_name = name
	item.item_group = group
	item.stock_uom = uom
	item.is_stock_item = 1
	item.is_purchase_item = 1
	item.is_sales_item = 0
	item.include_item_in_manufacturing = 1
	item.has_variants = 1
	item.variant_based_on = "Item Attribute"
	item.append("attributes", {"attribute": attribute})
	item.flags.ignore_permissions = True
	item.insert()
	return code


def _ensure_variant(code: str, template: str, attribute: str, value: str, group: str, uom: str, image: str | None = None):
	# Purely additive on re-run: an existing item's image is never touched here,
	# even to "fix" it to a newer default - the user may have deliberately replaced
	# it with their own photo, and re-seeding must never clobber that.
	if frappe.db.exists("Item", code):
		return code

	item = frappe.new_doc("Item")
	item.item_code = code
	item.item_name = f"{template} - {value}"
	item.item_group = group
	item.stock_uom = uom
	item.is_stock_item = 1
	item.is_purchase_item = 1
	item.is_sales_item = 0
	item.include_item_in_manufacturing = 1
	item.variant_of = template
	item.append("attributes", {"attribute": attribute, "attribute_value": value})
	if image:
		item.image = image
	item.flags.ignore_permissions = True
	item.insert()
	return code


def _ensure_item(code, name, group, uom, *, sales=False, purchase=False):
	if frappe.db.exists("Item", code):
		return code

	item = frappe.new_doc("Item")
	item.item_code = code
	item.item_name = name
	item.item_group = group
	item.stock_uom = uom
	item.is_stock_item = 1
	item.is_sales_item = 1 if sales else 0
	item.is_purchase_item = 1 if purchase else 0
	item.include_item_in_manufacturing = 1
	item.flags.ignore_permissions = True
	item.insert()
	return code


def _ensure_price(product, fabric, sublimation, rate, currency):
	existing = frappe.db.get_value(
		"VastraFlow Price Matrix",
		{
			"product_type": product,
			"fabric": fabric,
			"sublimation_type": sublimation,
			"docstatus": 1,
		},
	)
	if existing:
		return existing

	doc = frappe.new_doc("VastraFlow Price Matrix")
	doc.product_type = product
	doc.fabric = fabric
	doc.sublimation_type = sublimation
	doc.rate = rate
	doc.currency = currency
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc.name


def _ensure_bom_rule(product_type: str):
	if frappe.db.exists("VastraFlow BOM Rule", product_type):
		return product_type

	rule = frappe.new_doc("VastraFlow BOM Rule")
	rule.product_type = product_type
	rule.is_active = 1
	rule.description = "Starter recipe created by VastraFlow"
	rule.use_order_fabric = 1
	rule.fabric_qty_per_unit = 1.2
	rule.size_scaling = 1
	rule.base_size = "38"
	rule.fabric_per_size_step = 0.03
	# Harmless when an order has no collar_type: build_bom_items only adds a
	# collar line when the order actually specifies one.
	rule.include_collar = 1
	rule.collar_qty_per_unit = 1
	rule.append("components", {"item_code": "ST", "qty_per_unit": 25, "basis": "Per Garment"})
	rule.append("components", {"item_code": "BU", "qty_per_unit": 1, "basis": "Per Button"})
	rule.append("components", {"item_code": "LAB", "qty_per_unit": 1, "basis": "Per Garment"})
	rule.append("components", {"item_code": "PB", "qty_per_unit": 1, "basis": "Per Garment"})
	rule.flags.ignore_permissions = True
	rule.insert()
	return rule.name


def create_starter_data() -> dict:
	created = {"items": [], "prices": [], "rules": []}

	products_group = _ensure_item_group("Products")
	raw_group = _ensure_item_group("Raw Material")
	services_group = _ensure_item_group("Services")
	_ensure_uom("Nos")

	for name, values in ATTRIBUTES.items():
		_ensure_item_attribute(name, values)

	created["items"].append(_ensure_template_item("FB", "Fabric", raw_group, "Nos", "Fabric"))
	created["items"].append(_ensure_template_item("COLL", "Collar", services_group, "Nos", "Collar Type"))

	for code, (value, _sketch) in FABRIC_VARIANTS.items():
		created["items"].append(_ensure_variant(code, "FB", "Fabric", value, raw_group, "Nos"))

	for code, (value, filename) in COLLAR_VARIANTS.items():
		image = f"/assets/vastraflow/images/collars/{filename}" if filename else None
		created["items"].append(_ensure_variant(code, "COLL", "Collar Type", value, services_group, "Nos", image))

	for code, name in PRODUCTS:
		created["items"].append(_ensure_item(code, name, products_group, "Nos", sales=True, purchase=True))
	for code, name, uom in TRIMS:
		created["items"].append(_ensure_item(code, name, raw_group, uom, purchase=True))

	company = frappe.db.get_value("Company", {}, "name")
	currency = frappe.get_cached_value("Company", company, "default_currency") if company else "INR"

	for product, fabric, sublimation, rate in PRICES:
		created["prices"].append(_ensure_price(product, fabric, sublimation, rate, currency))

	for product, _ in PRODUCTS:
		created["rules"].append(_ensure_bom_rule(product))

	get_logger().info(
		f"Starter catalog loaded: {len(created['items'])} items, "
		f"{len(created['prices'])} prices, {len(created['rules'])} BOM rules"
	)
	return created
