"""Starter data so a fresh install can be exercised immediately.

Triggered from the Load Starter Data button on VastraFlow Settings. Everything is
created idempotently, so pressing it twice is harmless.

Item modelling note: finished garments are sales items, fabrics and trims are
purchase items. That is what makes them behave correctly on a Sales Order line and
inside a BOM respectively.
"""

import frappe

from vastraflow.apparel_core.logging_utils import get_logger

PRODUCTS = [
	("POLO", "Polo Shirt"),
	("TSHIRT", "Round Neck T-Shirt"),
]
FABRICS = [
	("FB-MICRO", "Micro Polyester"),
	("FB-COMBOLINE", "Comboline"),
	("FB-PN", "Pique Net"),
]
COLLARS = [
	("COLL-RN", "Round Neck Collar"),
	("COLL-VNE", "V-Neck Collar"),
]
# Thread is consumed fractionally, so it needs a UOM that allows fractions.
# "Nos" is flagged Must Be Whole Number in ERPNext and would reject 0.05.
TRIMS = [
	("VF-THREAD", "Stitching Thread", "Meter"),
	("VF-BUTTON", "Shirt Button", "Nos"),
	("VF-POLYBAG", "Packing Polybag", "Nos"),
]

PRICES = [
	("POLO", "FB-MICRO", "Plain", 150),
	("POLO", "FB-MICRO", "Full sublimation", 200),
	("POLO", "FB-COMBOLINE", "Plain", 165),
	("POLO", "FB-COMBOLINE", "Front Sublimation", 185),
	("TSHIRT", "FB-MICRO", "Plain", 110),
	("TSHIRT", "FB-PN", "Front Sublimation", 140),
]


def _ensure_item_group(name: str, parent: str = "All Item Groups"):
	if frappe.db.exists("Item Group", name):
		return name
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
	rule.fabric_uom = "Meter"
	rule.size_scaling = 1
	rule.base_size = "38"
	rule.fabric_per_size_step = 0.03
	rule.include_collar = 1
	rule.collar_qty_per_unit = 1
	rule.append("components", {"item_code": "VF-THREAD", "qty_per_unit": 25, "basis": "Per Garment"})
	rule.append("components", {"item_code": "VF-BUTTON", "qty_per_unit": 1, "basis": "Per Button"})
	rule.append("components", {"item_code": "VF-POLYBAG", "qty_per_unit": 1, "basis": "Per Garment"})
	rule.flags.ignore_permissions = True
	rule.insert()
	return rule.name


def create_starter_data() -> dict:
	created = {"items": [], "prices": [], "rules": []}

	products_group = _ensure_item_group("Products")
	raw_group = _ensure_item_group("Raw Material")
	_ensure_uom("Meter")
	_ensure_uom("Nos")

	for code, name in PRODUCTS:
		created["items"].append(_ensure_item(code, name, products_group, "Nos", sales=True))
	for code, name in FABRICS:
		created["items"].append(_ensure_item(code, name, raw_group, "Meter", purchase=True))
	for code, name in COLLARS:
		created["items"].append(_ensure_item(code, name, raw_group, "Nos", purchase=True))
	for code, name, uom in TRIMS:
		created["items"].append(_ensure_item(code, name, raw_group, uom, purchase=True))

	company = frappe.db.get_value("Company", {}, "name")
	currency = frappe.get_cached_value("Company", company, "default_currency") if company else "INR"

	for product, fabric, sublimation, rate in PRICES:
		created["prices"].append(_ensure_price(product, fabric, sublimation, rate, currency))

	for product, _ in PRODUCTS:
		created["rules"].append(_ensure_bom_rule(product))

	get_logger().info(
		f"Starter data loaded: {len(created['items'])} items, "
		f"{len(created['prices'])} prices, {len(created['rules'])} BOM rules"
	)
	return created
