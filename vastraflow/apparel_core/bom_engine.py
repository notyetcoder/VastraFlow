"""Automatic BOM generation.

The problem this solves: in apparel, a BOM per finished-goods combination is
unmanageable. Product type x fabric x collar x sleeve x stitching x buttons is
thousands of BOMs, and nobody is going to key those in by hand.

The approach: a single recipe per product type (VastraFlow BOM Rule) describes how
much of what is consumed per garment. When an order actually needs manufacturing,
the engine resolves that recipe against the order's specification, builds a real
ERPNext BOM, and stamps it with a signature. The next order with the same spec
reuses the stamped BOM instead of creating another.

The result is a normal, fully-costed ERPNext BOM that Work Orders, stock and
costing all understand - the user just never types one in.
"""

import hashlib
import math

import frappe
from frappe.utils import flt, now_datetime

from vastraflow.apparel_core.logging_utils import get_logger
from vastraflow.apparel_core.settings import get_settings, get_size_factor


def build_spec(doc) -> frappe._dict:
	"""The physical specification of a garment order, as the BOM engine sees it."""
	return frappe._dict(
		product_type=doc.get("product_type"),
		fabric=doc.get("fabric"),
		collar_type=doc.get("collar_type"),
		sleeve_type=doc.get("sleeve_type"),
		stitching_type=doc.get("stitching_type"),
		button_quantity=doc.get("button_quantity"),
		sublimation_type=doc.get("sublimation_type"),
		company=doc.get("company"),
	)


def get_bom_rule(product_type: str):
	"""The recipe for a product type, or None."""
	if not product_type:
		return None
	name = frappe.db.get_value("VastraFlow BOM Rule", {"product_type": product_type, "is_active": 1})
	return frappe.get_doc("VastraFlow BOM Rule", name) if name else None


def _button_count(button_quantity: str) -> float:
	return {"none": 0, "one": 1, "two": 2, "three": 3, "four": 4}.get(
		(button_quantity or "").strip().lower(), 0
	)


def weighted_average_size(doc, settings=None):
	"""Quantity-weighted average size across the order's matrix.

	Returns a float for numeric sizes, or None when sizes are not numeric.
	"""
	total_qty = 0.0
	weighted = 0.0

	for row in doc.get("size_matrix") or []:
		qty = flt(row.full_sleeve) + flt(row.half_sleeve) + flt(row.sleeveless)
		if qty <= 0:
			continue
		try:
			size_value = float(str(row.size).strip())
		except (TypeError, ValueError):
			return None
		weighted += size_value * qty
		total_qty += qty

	return (weighted / total_qty) if total_qty else None


def weighted_average_factor(doc, settings=None) -> float:
	"""Quantity-weighted fabric factor, for custom (non-numeric) size lists."""
	settings = settings or get_settings()
	total_qty = 0.0
	weighted = 0.0

	for row in doc.get("size_matrix") or []:
		qty = flt(row.full_sleeve) + flt(row.half_sleeve) + flt(row.sleeveless)
		if qty <= 0:
			continue
		weighted += get_size_factor(row.size, settings) * qty
		total_qty += qty

	return (weighted / total_qty) if total_qty else 1.0


def compute_fabric_qty(doc, rule, settings) -> float:
	"""Fabric consumed per garment, after any size scaling."""
	base = flt(rule.fabric_qty_per_unit) if rule else flt(settings.default_fabric_qty)
	if base <= 0:
		base = flt(settings.default_fabric_qty) or 1.0

	if not (rule and rule.size_scaling):
		return base

	if settings.size_mode == "Custom List":
		return base * weighted_average_factor(doc, settings)

	average = weighted_average_size(doc, settings)
	if average is None:
		return base

	try:
		base_size = float(str(rule.base_size).strip())
	except (TypeError, ValueError):
		base_size = 38.0

	step = float(settings.size_step or 2) or 2.0
	extra = flt(rule.fabric_per_size_step)
	return max(base + ((average - base_size) / step) * extra, 0.0)


def compute_signature(spec, settings, fabric_qty: float | None = None) -> str:
	"""Stable key for "two orders that can share one BOM"."""
	parts = [
		spec.product_type or "",
		spec.fabric or "",
		spec.collar_type or "",
		spec.sleeve_type or "",
		spec.stitching_type or "",
		spec.button_quantity or "",
		spec.company or "",
	]

	if settings.signature_includes_sublimation:
		parts.append(spec.sublimation_type or "")

	if settings.signature_includes_size_band and fabric_qty is not None:
		# Band by rounded consumption - the thing that actually differs.
		parts.append(f"{flt(fabric_qty, 2):.2f}")

	digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
	return f"VF-{digest}"


def _resolve_uom(item_code: str, wanted: str | None) -> str:
	"""Use the requested UOM only if the item can actually convert to it."""
	stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
	if not wanted or wanted == stock_uom:
		return stock_uom
	if frappe.db.exists("UOM Conversion Detail", {"parent": item_code, "uom": wanted}):
		return wanted
	return stock_uom


def _round_for_uom(uom: str | None, qty: float) -> float:
	"""Whole-number UOMs (Nos, Box...) reject fractions, so round consumption up.

	Rounding up is the correct direction for material planning - half a button
	still consumes a whole one.
	"""
	if not uom:
		return qty
	if frappe.db.get_value("UOM", uom, "must_be_whole_number"):
		return float(math.ceil(qty)) or 1.0
	return qty


def build_bom_items(doc, spec, rule, settings) -> list[dict]:
	"""Raw material lines for the generated BOM."""
	items: list[dict] = []

	# --- Fabric -------------------------------------------------------------
	fabric_item = spec.fabric
	if rule and not rule.use_order_fabric:
		fabric_item = rule.fixed_fabric_item

	if fabric_item:
		qty = compute_fabric_qty(doc, rule, settings)
		wanted_uom = (rule.fabric_uom if rule else None) or settings.default_fabric_uom
		uom = _resolve_uom(fabric_item, wanted_uom)
		items.append(
			{
				"item_code": fabric_item,
				"qty": _round_for_uom(uom, flt(qty, 4)) or 1.0,
				"uom": uom,
			}
		)

	# --- Collar -------------------------------------------------------------
	include_collar = rule.include_collar if rule else settings.include_collar_in_bom
	if include_collar and spec.collar_type:
		collar_qty = flt(rule.collar_qty_per_unit) if rule else flt(settings.default_collar_qty)
		collar_uom = _resolve_uom(spec.collar_type, None)
		items.append(
			{
				"item_code": spec.collar_type,
				"qty": _round_for_uom(collar_uom, collar_qty or 1.0),
				"uom": collar_uom,
			}
		)

	# --- Everything else from the recipe ------------------------------------
	for component in (rule.components if rule else []) or []:
		if component.apply_if_sleeve and component.apply_if_sleeve != "All":
			if component.apply_if_sleeve != spec.sleeve_type:
				continue

		qty = flt(component.qty_per_unit)
		if component.basis == "Per Button":
			qty *= _button_count(spec.button_quantity)

		if qty <= 0:
			continue

		component_uom = _resolve_uom(component.item_code, component.uom)
		items.append(
			{
				"item_code": component.item_code,
				"qty": _round_for_uom(component_uom, flt(qty, 4)),
				"uom": component_uom,
			}
		)

	return items


def find_existing_bom(signature: str, product_type: str) -> str | None:
	return frappe.db.get_value(
		"BOM",
		{
			"vastraflow_signature": signature,
			"item": product_type,
			"docstatus": 1,
			"is_active": 1,
		},
		"name",
	)


def get_or_create_bom(doc, raise_on_error: bool = True) -> str | None:
	"""Return a submitted BOM matching the order's specification, creating it if needed."""
	settings = get_settings()

	if not settings.enable_auto_bom:
		if raise_on_error:
			frappe.throw(frappe._("Automatic BOM is turned off in VastraFlow Settings."))
		return None

	spec = build_spec(doc)
	if not spec.product_type:
		if raise_on_error:
			frappe.throw(frappe._("Product Type is required before a BOM can be generated."))
		return None

	rule = get_bom_rule(spec.product_type)
	if not rule and settings.bom_missing_rule_action == "Block With Error":
		frappe.throw(
			frappe._(
				"No active VastraFlow BOM Rule exists for <b>{0}</b>. "
				"Create one, or set <i>When No BOM Rule Exists</i> to "
				"<i>Use Defaults Below</i> in VastraFlow Settings."
			).format(spec.product_type)
		)

	fabric_qty = compute_fabric_qty(doc, rule, settings)
	signature = compute_signature(spec, settings, fabric_qty)

	if settings.reuse_matching_bom:
		existing = find_existing_bom(signature, spec.product_type)
		if existing:
			get_logger().info(f"Reusing BOM {existing} for {doc.get('name')} ({signature})")
			return existing

	items = build_bom_items(doc, spec, rule, settings)
	if not items:
		msg = frappe._(
			"Cannot build a BOM for <b>{0}</b>: the recipe produced no raw materials. "
			"Check the fabric on the order and the VastraFlow BOM Rule."
		).format(spec.product_type)
		if raise_on_error:
			frappe.throw(msg)
		get_logger().error(msg)
		return None

	company = settings.bom_company or spec.company or frappe.defaults.get_user_default("Company")
	currency = settings.bom_currency or frappe.get_cached_value("Company", company, "default_currency")

	bom = frappe.new_doc("BOM")
	bom.item = spec.product_type
	bom.company = company
	bom.currency = currency
	bom.quantity = 1
	bom.is_active = 1
	# Do not silently steal "default BOM" from an existing one.
	bom.is_default = 0 if frappe.db.exists("BOM", {"item": spec.product_type, "is_default": 1}) else 1
	bom.with_operations = 0
	bom.rm_cost_as_per = "Valuation Rate"
	bom.vastraflow_signature = signature
	bom.vastraflow_auto_generated = 1

	for item in items:
		bom.append("items", item)

	bom.flags.ignore_permissions = True
	bom.insert()

	if settings.auto_submit_bom:
		bom.submit()

	get_logger().info(
		f"Generated BOM {bom.name} for {doc.get('name')} | {spec.product_type} / {spec.fabric} "
		f"| signature {signature} | {len(items)} components"
	)
	return bom.name


def _pick_warehouse(company: str, preferred: str, item_code: str | None = None) -> str | None:
	"""Best available warehouse: the item's default, then the conventional ERPNext
	one, then any non-group warehouse for the company."""
	if item_code:
		item_default = frappe.db.get_value(
			"Item Default", {"parent": item_code, "company": company}, "default_warehouse"
		)
		if item_default:
			return item_default

	by_name = frappe.db.get_value(
		"Warehouse", {"company": company, "warehouse_name": preferred, "is_group": 0}, "name"
	)
	if by_name:
		return by_name

	return frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")


def _default_warehouses(company: str, item_code: str | None = None) -> dict:
	"""Work Order warehouses. Left blank if nothing sensible exists - the draft
	still saves and the user picks them before submitting."""
	return {
		"wip_warehouse": _pick_warehouse(company, "Work In Progress"),
		"fg_warehouse": _pick_warehouse(company, "Finished Goods", item_code),
	}


def create_work_order(doc, qty: float | None = None) -> str:
	"""Create a draft Work Order for a garment order, generating the BOM if needed."""
	settings = get_settings()
	bom_no = get_or_create_bom(doc)

	if qty is None:
		if settings.work_order_qty_source == "Sales Order Item Qty":
			qty = sum(flt(row.qty) for row in doc.get("items") or [])
		else:
			qty = flt(doc.get("garment_total_qty"))

	qty = flt(qty)
	if qty <= 0:
		frappe.throw(frappe._("Quantity for the Work Order must be greater than zero."))

	company = settings.bom_company or doc.get("company")
	warehouses = _default_warehouses(company, doc.get("product_type"))

	work_order = frappe.new_doc("Work Order")
	work_order.production_item = doc.get("product_type")
	work_order.bom_no = bom_no
	work_order.qty = qty
	work_order.company = company
	work_order.sales_order = doc.get("name")
	work_order.planned_start_date = now_datetime()

	if warehouses.get("wip_warehouse"):
		work_order.wip_warehouse = warehouses["wip_warehouse"]
	if warehouses.get("fg_warehouse"):
		work_order.fg_warehouse = warehouses["fg_warehouse"]

	work_order.flags.ignore_permissions = True
	work_order.insert()

	get_logger().info(f"Created Work Order {work_order.name} from {doc.get('name')} using BOM {bom_no}")
	return work_order.name


# --- Whitelisted entry points ------------------------------------------------


@frappe.whitelist()
def ensure_bom_for_sales_order(sales_order: str):
	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")
	bom_no = get_or_create_bom(doc)
	return {"bom_no": bom_no}


@frappe.whitelist()
def create_work_order_for_sales_order(sales_order: str, qty: float | None = None):
	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")

	if doc.docstatus != 1:
		frappe.throw(frappe._("Submit the Sales Order before creating a Work Order."))

	name = create_work_order(doc, flt(qty) if qty else None)
	return {"work_order": name}


@frappe.whitelist()
def preview_bom(sales_order: str):
	"""What the generated BOM would contain, without creating anything."""
	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")

	settings = get_settings()
	spec = build_spec(doc)
	rule = get_bom_rule(spec.product_type)
	fabric_qty = compute_fabric_qty(doc, rule, settings)
	signature = compute_signature(spec, settings, fabric_qty)

	return {
		"signature": signature,
		"rule": rule.name if rule else None,
		"existing_bom": find_existing_bom(signature, spec.product_type),
		"items": build_bom_items(doc, spec, rule, settings),
	}
