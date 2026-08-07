"""Single source of truth for P3 pricing calculations.

Both the real order-submission flow (vastraflow.py) and the interactive
Price Calculator page call INTO these same functions - never two separate
implementations of "how price is computed." That's deliberate: a
calculator that can silently drift from what orders actually get charged
is worse than no calculator at all.

Priority tiers, checked in this fixed order (matches the spec: Customer
Rule -> Product Rule -> Global Rule -> Default):

  1. Fabric + Product Type + Customer  (most specific override)
  2. Fabric + Customer (any product)
  3. Fabric + Product Type (any customer)
  4. Fabric only (Global rate)
  5. Default: no match -> price is simply unknown (never guessed, never
     silently zero - the caller decides whether that blocks a submit or
     just shows "no base price yet" in the calculator).
"""

import frappe

# Attribute -> the value the caller is expected to supply for it, and
# what P3 Price Adjustment's spec_value should be compared against.
ADJUSTMENT_ATTRIBUTES = [
	"Sublimation", "Size", "Sleeve Type", "Button",
	"Collar Type", "Stitching Type", "Thread Color", "Packaging", "Label", "Neck Tape",
]


def get_base_rate(fabric, product_type=None, customer=None):
	"""Returns a dict {rate, currency, source, name} or None if nothing
	matches at any tier.
	"""
	if not fabric:
		return None

	tiers = []
	if customer and product_type:
		tiers.append((
			{"fabric": fabric, "product_type": product_type, "customer": customer},
			"Customer Rule (product-specific)",
		))
	if customer:
		tiers.append((
			{"fabric": fabric, "product_type": "", "customer": customer},
			"Customer Rule",
		))
	if product_type:
		tiers.append((
			{"fabric": fabric, "product_type": product_type, "customer": ""},
			"Product Rule",
		))
	tiers.append((
		{"fabric": fabric, "product_type": "", "customer": ""},
		"Global Rule",
	))

	for filters, source in tiers:
		filters["is_active"] = 1
		row = frappe.db.get_value(
			"P3 Base Price", filters, ["name", "rate", "currency"], as_dict=True
		)
		if row:
			return {"rate": row.rate or 0, "currency": row.currency, "source": source, "name": row.name}

	return None


def is_attribute_price_enabled(attribute_name):
	return bool(frappe.db.get_value("P3 Price Attribute Toggle", attribute_name, "affects_price"))


def get_adjustment(attribute_name, spec_value):
	"""Returns {amount, currency, name} or None - a missing row is NOT an
	error anywhere in this system, it just means +0 for that attribute.
	Also returns None (silently) if the attribute's Affects Price toggle
	is off, regardless of whether an adjustment row happens to exist for
	it - toggled-off attributes are invisible to pricing entirely.
	"""
	if not attribute_name or not spec_value:
		return None
	if not is_attribute_price_enabled(attribute_name):
		return None
	return frappe.db.get_value(
		"P3 Price Adjustment",
		{"attribute_name": attribute_name, "spec_value": spec_value, "is_active": 1},
		["name", "amount", "currency"],
		as_dict=True,
	)


def calculate_price(fabric, product_type=None, customer=None, spec_values=None):
	"""spec_values: dict of {attribute_name: value} for any subset of
	ADJUSTMENT_ATTRIBUTES - e.g. {"Sublimation": "Front Sublimation",
	"Size": "XXL"}. Missing/None values are simply skipped.

	Returns a full breakdown dict - used as-is by the Price Calculator's
	whitelisted endpoint, and consumed field-by-field by P3OrderBook's
	real pricing methods.
	"""
	spec_values = spec_values or {}

	base = get_base_rate(fabric, product_type, customer)

	adjustments = []
	adjustment_total = 0
	for attribute_name in ADJUSTMENT_ATTRIBUTES:
		value = spec_values.get(attribute_name)
		if not value:
			continue
		enabled = is_attribute_price_enabled(attribute_name)
		adj = get_adjustment(attribute_name, value) if enabled else None
		adjustments.append(
			{
				"attribute": attribute_name,
				"value": value,
				"amount": (adj.amount if adj else 0) or 0,
				"price_enabled": enabled,
				"matched": bool(adj),
			}
		)
		if adj:
			adjustment_total += adj.amount or 0

	base_rate = base["rate"] if base else None
	total = (base_rate + adjustment_total) if base_rate is not None else None

	return {
		"base_rate": base_rate,
		"base_source": base["source"] if base else None,
		"base_price_name": base["name"] if base else None,
		"currency": base["currency"] if base else "INR",
		"adjustments": adjustments,
		"adjustment_total": adjustment_total,
		"total": total,
		"missing_base_price": base is None,
	}


@frappe.whitelist()
def calculate_price_api(fabric, product_type=None, customer=None, spec_values=None):
	"""Whitelisted entry point for the Price Calculator page. spec_values
	arrives as a JSON string from the client.
	"""
	import json

	if isinstance(spec_values, str):
		spec_values = json.loads(spec_values) if spec_values else {}
	return calculate_price(fabric, product_type or None, customer or None, spec_values)
