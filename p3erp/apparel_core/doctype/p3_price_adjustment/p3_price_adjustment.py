import frappe
from frappe import _
from frappe.model.document import Document


class P3PriceAdjustment(Document):
	"""Universal, additive price impact for one specific attribute value
	(e.g. Sublimation = "Front Only" -> +15), NOT scoped to a Product Type.
	This is deliberately independent of P3BasePrice - the whole point of
	splitting Base from Adjustments is to avoid needing every possible
	Product x Fabric x Size x Sleeve x ... combination priced explicitly.
	A missing adjustment row is NOT an error - it's treated as +0 (see
	P3OrderBook.get_price_adjustment_total()) - only Base Price is a hard
	submit-blocking requirement. Also gated by P3PriceAttributeToggle: if
	an attribute's "Affects Price" toggle is off, its adjustment rows
	(even if present) are never looked up at all.
	"""

	def validate(self):
		self._check_duplicate()

	def _check_duplicate(self):
		existing = frappe.db.exists(
			"P3 Price Adjustment",
			{
				"attribute_name": self.attribute_name,
				"spec_value": self.spec_value,
				"is_active": 1,
				"name": ["!=", self.name],
			},
		)
		if existing and self.is_active:
			frappe.throw(
				_(
					"An active adjustment already exists for {0} = '{1}': {2}. Deactivate it "
					"first, or edit it directly instead of creating a duplicate."
				).format(self.attribute_name, self.spec_value, existing)
			)
