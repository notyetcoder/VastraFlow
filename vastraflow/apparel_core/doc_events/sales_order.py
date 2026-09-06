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


# Sublimation types that fix (lock) the front / back panel to the print, leaving only
# the other panels open for a Colour/A4 choice. Mirrors FRONT_LOCKED / BACK_LOCKED in
# custom_fields.py - kept in sync manually since one is a Python set and the other a
# client-side eval string.
_FRONT_LOCKED = {"Front Sublimation", "Front & Back sublimation", "Full sublimation"}
_BACK_LOCKED = {"Back Sublimation", "Front & Back sublimation", "Full sublimation"}
_ANY_SUBLIMATION = _FRONT_LOCKED | _BACK_LOCKED


def _normalize_panels(doc):
	"""Clear Front/Back/Sleeve panel fields that no longer apply, so stale data from
	a previous Sublimation Type or Sleeve Type selection is never carried forward or
	printed. The client only *blocks editing* of a locked panel (read_only_depends_on)
	rather than hiding it, so a value set before the lock kicked in would otherwise
	survive untouched - this is what actually clears it.

	Border Colour and Collar Colour have no lock/treatment step at all (see
	custom_fields.py) - just plain optional colours, nothing to normalize here."""
	sublimation = doc.get("sublimation_type")

	# "None" is a non-empty string - checking truthiness alone (the bug this fixed)
	# treated "no sublimation" as "sublimation is happening". Must check membership
	# in _ANY_SUBLIMATION instead.
	front_open = sublimation in _ANY_SUBLIMATION and sublimation not in _FRONT_LOCKED
	back_open = sublimation in _ANY_SUBLIMATION and sublimation not in _BACK_LOCKED
	sleeve_open = sublimation in _ANY_SUBLIMATION and doc.get("sleeve_type") != "Sleeveless"

	for open_, treatment_field, colour_field in (
		(front_open, "front_treatment", "front_colour"),
		(back_open, "back_treatment", "back_colour"),
		(sleeve_open, "sleeve_treatment", "sleeve_colour"),
	):
		if not open_:
			doc.set(treatment_field, "")
			doc.set(colour_field, "")
		elif doc.get(treatment_field) != "Colour":
			doc.set(colour_field, "")


def _product_item(doc) -> str | None:
	"""The finished garment for this order - the first row of the standard Items
	table. The user picks it there, the normal ERPNext way; nothing else asks for it
	a second time."""
	rows = doc.get("items") or []
	return rows[0].item_code if rows else None


def _sync_item_line(doc, total_qty, rate):
	"""Keep the garment's Item line in step with the matrix total and matched rate.

	Only qty/uom/rate are ours to set - item_code is the user's own pick in the
	Items table and is never touched here."""
	row = (doc.get("items") or [None])[0]
	if row is None or total_qty <= 0:
		return

	stock_uom = frappe.db.get_value("Item", row.item_code, "stock_uom")
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

	# Auto-synced mirror of the Items table's first row - see _product_item. Done
	# first so every check and lookup below (pricing, BOM matching, the report, the
	# print format) sees it, exactly as if it were still typed in directly.
	doc.product_type = _product_item(doc)

	_ensure_size_matrix(doc, settings)
	_normalize_sleeves(doc)
	_normalize_panels(doc)

	total_qty = _total_qty(doc)
	doc.garment_total_qty = total_qty

	# Completeness (product/fabric/sublimation/sleeve set, quantities entered) is
	# only enforced at submit - see before_submit. A draft must stay freely saveable
	# while it's being built up over several saves, same as any other Sales Order.
	# It matters in practice: Frappe's Attach control calls frm.save() the instant a
	# file is picked (frappe/public/js/frappe/form/controls/attach.js), so attaching
	# artwork before the Size Matrix is filled in used to trigger this exact check
	# and block on an unrelated action.
	rate = get_price_for_order(doc)
	doc.vf_matched_rate = rate or 0
	doc.garmentos_price_status = "Priced" if rate else "Missing Price"

	if settings.auto_create_item_line:
		_sync_item_line(doc, total_qty, rate)


def _validate_specification(doc, total_qty):
	if not doc.get("product_type"):
		frappe.throw(
			frappe._("Add the garment to the <b>Items</b> table before saving."),
			title=frappe._("No Item Selected"),
		)

	missing = [
		label
		for field, label in (
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

	# The order must be complete before it becomes a real, submitted document -
	# checked here (not on every draft save) so building it up over several saves
	# (e.g. attaching artwork before the Size Matrix is filled in) is never blocked.
	_validate_specification(doc, _total_qty(doc))

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
