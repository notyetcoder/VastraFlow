import frappe
from frappe import _
from frappe.model.document import Document


class P3Surcharge(Document):
	"""Additive add-on price for a specific Collar Type / Stitching Type /
	Sublimation Type value on a given Product Type. Deliberately separate
	from P3BasePrice: most collar/stitching/sublimation choices don't
	actually change cost, so treating them as an independent multiplying
	dimension in the base price table would force pricing thousands of
	combinations that never need distinct prices. Missing a surcharge row
	for a given value is NOT an error - it defaults to zero (see
	P3OrderBook.get_surcharge()). Only the base rate (P3BasePrice) is a
	hard submit-blocking requirement.
	"""

	def validate(self):
		if self.amount is not None and self.amount < 0:
			frappe.throw(_("Surcharge amount cannot be negative."))
		self._check_duplicate()

	def _check_duplicate(self):
		existing = frappe.db.exists(
			"P3 Surcharge",
			{
				"product_type": self.product_type,
				"applies_to": self.applies_to,
				"spec_value": self.spec_value,
				"is_active": 1,
				"name": ["!=", self.name],
			},
		)
		if existing and self.is_active:
			frappe.throw(
				_(
					"An active surcharge already exists for this exact Product Type + {0} + '{1}': {2}. "
					"Deactivate it first, or edit it directly instead of creating a duplicate."
				).format(self.applies_to, self.spec_value, existing)
			)
