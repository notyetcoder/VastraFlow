"""Single source of truth for P3 pricing calculations.

Both the real order-submission flow (vastraflaw_order_book.py) and the
whitelisted calculate_price_api() below call INTO this same function -
never two separate implementations of "how price is computed."

The pricing model is deliberately simple: Fabric x Sublimation Type ->
Rate (see P3 Price List). Nothing else affects price - Collar Type,
Stitching Type, Size, Sleeve Type, Button Qty etc. are production specs
only and carry zero price impact. A whole vastraflaw Order Book document
therefore has exactly ONE rate, applied to every matrix cell/line item on
it, since Fabric and Sublimation Type are both order-level (not
per-cell) fields.

Missing base price is never guessed and never silently zero - the caller
(before_submit) decides whether that blocks a submit.
"""

import frappe


def get_base_rate(fabric, sublimation_type):
	"""Returns a dict {rate, currency, name} or None if no active P3
	Price List row matches this exact Fabric + Sublimation Type pair.
	"""
	if not fabric or not sublimation_type:
		return None

	return frappe.db.get_value(
		"P3 Price List",
		{"fabric": fabric, "sublimation_type": sublimation_type, "is_active": 1},
		["name", "rate", "currency"],
		as_dict=True,
	)


def calculate_price(fabric, sublimation_type):
	"""Returns a breakdown dict - used as-is by the whitelisted endpoint
	below and by vastraflawOrderBook.get_price().
	"""
	base = get_base_rate(fabric, sublimation_type)

	return {
		"base_rate": base.rate if base else None,
		"currency": base.currency if base else "INR",
		"price_list_name": base.name if base else None,
		"total": base.rate if base else None,
		"missing_base_price": base is None,
	}


@frappe.whitelist()
def calculate_price_api(fabric, sublimation_type):
	"""Whitelisted entry point, used by the P3 Price List form/list if a
	quick "what would this charge" check is ever wired up client-side.
	"""
	return calculate_price(fabric, sublimation_type)
