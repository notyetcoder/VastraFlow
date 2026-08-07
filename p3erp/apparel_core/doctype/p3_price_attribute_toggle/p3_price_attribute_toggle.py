from frappe.model.document import Document


class P3PriceAttributeToggle(Document):
	"""One row per attribute category (Fabric, Sublimation, Size, etc.)
	with a single Affects Price checkbox. This is checked by
	P3OrderBook.get_price_adjustment_total() before looking for a matching
	P3 Price Adjustment row - if an attribute is toggled off here, it's
	skipped entirely for pricing purposes regardless of what P3 Price
	Adjustment rows exist for it. This is what makes new attributes
	(Thread Color, Packaging, Label, Neck Tape, ...) safe to add as pure
	production specs today and switch on for pricing later without any
	code change - just flip the checkbox once a real P3 Price Adjustment
	row exists for it.
	"""

	pass
