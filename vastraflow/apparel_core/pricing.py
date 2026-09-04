"""Price lookup against the VastraFlow Price Matrix."""

import frappe

from vastraflow.apparel_core.logging_utils import get_logger


def get_price_for_order(doc):
	"""Return the matrix rate for an order's specification, or None.

	Matching is exact on product type + fabric + sublimation type, and only
	submitted (docstatus 1) matrix rows are considered.
	"""
	if not (doc.get("product_type") and doc.get("fabric") and doc.get("sublimation_type")):
		return None

	try:
		# get_value with a single fieldname returns the scalar, not a row.
		rate = frappe.db.get_value(
			"VastraFlow Price Matrix",
			{
				"product_type": doc.product_type,
				"fabric": doc.fabric,
				"sublimation_type": doc.sublimation_type,
				"docstatus": 1,
			},
			"rate",
			order_by="modified desc",
		)
		return float(rate) if rate is not None else None
	except Exception as exc:
		get_logger().error(f"Price lookup failed for {doc.get('name')}: {exc}")
		frappe.log_error(frappe.get_traceback(), "VastraFlow: price lookup")
		return None


def describe_missing_price(doc) -> str:
	return frappe._(
		"No price found in the VastraFlow Price Matrix for this combination:"
		"<br><br><b>Product Type:</b> {0}<br><b>Fabric:</b> {1}<br><b>Sublimation:</b> {2}"
		"<br><br>Create a submitted Price Matrix entry for it, or turn off "
		"<i>Block Submit Without Price</i> in VastraFlow Settings to enter the rate by hand."
	).format(
		doc.get("product_type") or "-",
		doc.get("fabric") or "-",
		doc.get("sublimation_type") or "-",
	)


@frappe.whitelist()
def preview_price(product_type: str, fabric: str, sublimation_type: str):
	"""Live price preview for the Sales Order form."""
	stub = frappe._dict(
		product_type=product_type,
		fabric=fabric,
		sublimation_type=sublimation_type,
		name="(preview)",
	)
	rate = get_price_for_order(stub)
	return {"rate": rate, "found": rate is not None}
