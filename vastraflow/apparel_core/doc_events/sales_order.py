"""Sales Order behaviour for garment orders.

Every handler starts with `_active(doc)`. If the order is not flagged as a garment
order - or VastraFlow is switched off in Settings - none of this runs and the Sales
Order behaves exactly like stock ERPNext.

Hook ordering note: Frappe runs the controller method first and the app hook second.
So anything that has to influence ERPNext's own totals (building the item line) is
done in `before_validate`, not `validate`.
"""

import frappe
from frappe.utils import flt

from vastraflow.apparel_core.logging_utils import get_logger
from vastraflow.apparel_core.pricing import describe_missing_price, get_price_for_order
from vastraflow.apparel_core.settings import get_settings, get_size_labels

SLEEVE_COLUMNS = {
	"Full Sleeve": "full_sleeve",
	"Half Sleeve": "half_sleeve",
	"Sleeveless": "sleeveless",
}
ALL_SLEEVE_COLUMNS = ("full_sleeve", "half_sleeve", "sleeveless")


def _active(doc) -> bool:
	"""True only for garment orders while the app is enabled."""
	if not doc.get("is_garment_order"):
		return False
	try:
		return bool(get_settings().enabled)
	except Exception:
		return False


# --- helpers -----------------------------------------------------------------


def _ensure_size_matrix(doc, settings):
	"""Fill an empty grid with the configured sizes. Never touches entered data."""
	if not settings.auto_populate_size_matrix:
		return
	if doc.get("size_matrix"):
		return

	for label in get_size_labels(settings):
		doc.append(
			"size_matrix",
			{"size": label, "full_sleeve": 0, "half_sleeve": 0, "sleeveless": 0, "row_total": 0},
		)

	doc.garmentos_generated = 1
	get_logger().info(f"Size matrix populated for {doc.get('name') or 'new order'}: {len(doc.size_matrix)} rows")


def _normalize_sleeves(doc):
	"""Zero the sleeve columns that do not apply to the selected sleeve type."""
	keep = SLEEVE_COLUMNS.get(doc.get("sleeve_type"))
	for row in doc.get("size_matrix") or []:
		if keep:
			for column in ALL_SLEEVE_COLUMNS:
				if column != keep:
					row.set(column, 0)
		row.row_total = sum(int(flt(row.get(c))) for c in ALL_SLEEVE_COLUMNS)


def _total_qty(doc) -> int:
	return sum(int(flt(row.get(c))) for row in (doc.get("size_matrix") or []) for c in ALL_SLEEVE_COLUMNS)


def _sync_item_line(doc, total_qty, rate):
	"""Keep one Sales Order Item in step with the matrix total and matched rate."""
	if not doc.get("product_type") or total_qty <= 0:
		return

	row = next((r for r in (doc.get("items") or []) if r.get("vf_generated")), None)
	if row is None:
		row = next((r for r in (doc.get("items") or []) if r.item_code == doc.product_type), None)

	if row is None:
		row = doc.append("items", {})
		row.item_code = doc.product_type

	# The item changed on an existing garment order - repoint the generated line.
	if row.get("vf_generated") and row.item_code != doc.product_type:
		row.item_code = doc.product_type

	stock_uom = frappe.db.get_value("Item", doc.product_type, "stock_uom")
	row.vf_generated = 1
	row.qty = total_qty
	if stock_uom:
		row.uom = stock_uom
		row.conversion_factor = 1
	if rate:
		row.rate = rate
	if doc.get("delivery_date") and not row.get("delivery_date"):
		row.delivery_date = doc.delivery_date


# --- hooks -------------------------------------------------------------------


def before_validate(doc, method=None):
	if not _active(doc):
		return

	settings = get_settings()

	_ensure_size_matrix(doc, settings)
	_normalize_sleeves(doc)

	total_qty = _total_qty(doc)
	doc.garment_total_qty = total_qty

	# Checked here rather than in `validate` so the user gets this message before
	# ERPNext tries to process an order with no item lines.
	_validate_specification(doc, total_qty)

	rate = get_price_for_order(doc)
	doc.vf_matched_rate = rate or 0
	doc.garmentos_price_status = "Priced" if rate else "Missing Price"

	if settings.auto_create_item_line:
		_sync_item_line(doc, total_qty, rate)


def _validate_specification(doc, total_qty):
	missing = [
		label
		for field, label in (
			("product_type", "Product Type"),
			("fabric", "Fabric"),
			("sublimation_type", "Sublimation Type"),
			("sleeve_type", "Sleeve Type"),
		)
		if not doc.get(field)
	]
	if missing:
		frappe.throw(
			frappe._("These garment fields are required: <b>{0}</b>").format(", ".join(missing)),
			title=frappe._("Incomplete Garment Specification"),
		)

	if not doc.get("size_matrix"):
		frappe.throw(
			frappe._("The Size Matrix is empty. Enter quantities before saving."),
			title=frappe._("Nothing to Produce"),
		)

	if flt(total_qty) <= 0:
		frappe.throw(
			frappe._(
				"Total quantity in the Size Matrix is zero. Enter quantities in the "
				"<b>{0}</b> column."
			).format(doc.get("sleeve_type") or frappe._("sleeve")),
			title=frappe._("Nothing to Produce"),
		)


def validate(doc, method=None):
	if not _active(doc):
		return

	_validate_artwork(doc, get_settings())

	get_logger().info(
		f"Validated {doc.get('name')} | {doc.product_type} / {doc.fabric} / {doc.sublimation_type} "
		f"| {doc.garment_total_qty} pcs | {doc.sleeve_type}"
	)


def _validate_artwork(doc, settings):
	mode = settings.artwork_enforcement or "Warn Only"
	if mode == "Ignore":
		return

	plain = (settings.plain_option_value or "Plain").strip()
	if doc.get("sublimation_type") == plain or doc.get("artwork_file"):
		return

	message = frappe._(
		"Sublimation is set to <b>{0}</b> but no artwork file is attached."
	).format(doc.get("sublimation_type"))

	if mode == "Block Submit" and doc.docstatus == 1:
		frappe.throw(message, title=frappe._("Artwork Required"))

	get_logger().warning(f"{doc.get('name')}: {doc.get('sublimation_type')} without artwork")
	frappe.msgprint(message, indicator="orange", alert=True)


def before_submit(doc, method=None):
	if not _active(doc):
		return

	settings = get_settings()
	rate = get_price_for_order(doc)

	if not rate:
		doc.garmentos_price_status = "Missing Price"
		if settings.block_submit_without_price:
			get_logger().error(
				f"No price for {doc.name}: {doc.product_type} + {doc.fabric} + {doc.sublimation_type}"
			)
			frappe.throw(describe_missing_price(doc), title=frappe._("No Matching Price"))

		frappe.msgprint(
			frappe._("Submitting without a Price Matrix match. The rate entered on the item line is used."),
			indicator="orange",
			alert=True,
		)
		return

	doc.vf_matched_rate = rate
	doc.garmentos_price_status = "Priced"
	get_logger().info(f"Price confirmed for {doc.name}: {rate}")


def on_submit(doc, method=None):
	if not _active(doc):
		return

	get_logger().info(f"Garment order submitted: {doc.name} | {doc.product_type} | {doc.customer}")

	settings = get_settings()
	if not (settings.enable_auto_bom and settings.auto_create_work_order):
		return

	# A failure here must not roll back a valid Sales Order submission.
	try:
		from vastraflow.apparel_core.bom_engine import create_work_order

		name = create_work_order(doc)
		frappe.msgprint(
			frappe._("Work Order {0} created.").format(
				f"<a href='/app/work-order/{name}'><b>{name}</b></a>"
			),
			indicator="green",
			alert=True,
		)
	except Exception as exc:
		get_logger().error(f"Auto Work Order failed for {doc.name}: {exc}")
		frappe.log_error(frappe.get_traceback(), "VastraFlow: auto work order")
		frappe.msgprint(
			frappe._("Sales Order submitted, but the Work Order could not be created: {0}").format(exc),
			indicator="red",
		)


def on_update_after_submit(doc, method=None):
	if _active(doc):
		get_logger().info(f"Garment order updated after submit: {doc.name}")


def before_cancel(doc, method=None):
	if _active(doc):
		get_logger().warning(f"Garment order being cancelled: {doc.name}")


def on_cancel(doc, method=None):
	if _active(doc):
		get_logger().warning(f"Garment order cancelled: {doc.name}")
