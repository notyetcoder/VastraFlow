"""Size-wise Order Summary.

Pivots garment order quantities into one column per size, so production can see
the whole size curve for a specification at a glance. Size columns come from
VastraFlow Settings, so a site using S/M/L/XL gets those columns instead.
"""

import frappe
from frappe.utils import flt

from vastraflow.apparel_core.settings import get_size_labels


def execute(filters=None):
	filters = frappe._dict(filters or {})
	sizes = get_size_labels()
	return get_columns(sizes), get_data(filters, sizes)


def get_columns(sizes):
	columns = [
		{"label": "Product Type", "fieldname": "product_type", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": "Fabric", "fieldname": "fabric", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": "Sublimation", "fieldname": "sublimation_type", "fieldtype": "Data", "width": 150},
		{"label": "Sleeve", "fieldname": "sleeve_type", "fieldtype": "Data", "width": 100},
	]
	columns += [
		{"label": str(size), "fieldname": f"size_{size}", "fieldtype": "Int", "width": 65}
		for size in sizes
	]
	columns.append({"label": "Total", "fieldname": "total", "fieldtype": "Int", "width": 90})
	return columns


def get_data(filters, sizes):
	conditions = {"is_garment_order": 1, "docstatus": ["<", 2]}

	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("product_type"):
		conditions["product_type"] = filters.product_type
	if filters.get("status"):
		conditions["status"] = filters.status
	if filters.get("from_date") and filters.get("to_date"):
		conditions["transaction_date"] = ["between", [filters.from_date, filters.to_date]]

	orders = frappe.get_all(
		"Sales Order",
		filters=conditions,
		fields=["name", "product_type", "fabric", "sublimation_type", "sleeve_type"],
	)
	if not orders:
		return []

	order_map = {o.name: o for o in orders}
	rows = frappe.get_all(
		"Sales Order Size Matrix",
		filters={"parent": ["in", list(order_map)], "parenttype": "Sales Order"},
		fields=["parent", "size", "full_sleeve", "half_sleeve", "sleeveless"],
	)

	valid_sizes = set(sizes)
	buckets: dict[tuple, dict] = {}

	for row in rows:
		qty = int(flt(row.full_sleeve) + flt(row.half_sleeve) + flt(row.sleeveless))
		if qty <= 0:
			continue

		order = order_map[row.parent]
		key = (order.product_type, order.fabric, order.sublimation_type, order.sleeve_type)

		bucket = buckets.setdefault(
			key,
			{
				"product_type": order.product_type,
				"fabric": order.fabric,
				"sublimation_type": order.sublimation_type,
				"sleeve_type": order.sleeve_type,
				"total": 0,
			},
		)

		# Sizes no longer in Settings still carry history - keep them in the total.
		if str(row.size) in valid_sizes:
			field = f"size_{row.size}"
			bucket[field] = bucket.get(field, 0) + qty
		bucket["total"] += qty

	return sorted(buckets.values(), key=lambda r: (-r["total"], r["product_type"] or ""))
