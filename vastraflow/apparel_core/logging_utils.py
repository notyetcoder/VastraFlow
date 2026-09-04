"""Logging helpers for VastraFlow."""

import frappe

LOGGER_NAME = "vastraflow"


def get_logger():
	return frappe.logger(LOGGER_NAME, allow_site=True, file_count=5)


def log_info(message: str):
	get_logger().info(message)


def log_warning(message: str):
	get_logger().warning(message)


def log_error(message: str, with_traceback: bool = False):
	get_logger().error(message)
	if with_traceback:
		frappe.log_error(frappe.get_traceback(), f"VastraFlow: {message[:100]}")


@frappe.whitelist()
def get_recent_activity(limit: int = 30):
	"""Recent VastraFlow-related activity for the Settings Activity tab.

	Reads the Error Log and Version tables rather than the log file, since the log
	file is not readable from the browser.
	"""
	limit = min(int(limit or 30), 100)

	errors = frappe.get_all(
		"Error Log",
		filters={"error": ["like", "%VastraFlow%"]},
		fields=["name", "creation", "method as title"],
		order_by="creation desc",
		limit=limit,
	)

	orders = frappe.get_all(
		"Sales Order",
		filters={"is_garment_order": 1},
		fields=["name", "modified", "status", "product_type", "garment_total_qty"],
		order_by="modified desc",
		limit=limit,
	)

	boms = frappe.get_all(
		"BOM",
		filters={"vastraflow_auto_generated": 1},
		fields=["name", "creation", "item", "docstatus"],
		order_by="creation desc",
		limit=limit,
	)

	return {"errors": errors, "orders": orders, "boms": boms}
