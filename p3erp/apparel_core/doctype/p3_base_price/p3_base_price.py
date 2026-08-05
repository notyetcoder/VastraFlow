import frappe
from frappe import _
from frappe.model.document import Document


class P3BasePrice(Document):
	"""Base rate for a (Product Type, Fabric, Sleeve Type, Size) combination.
	This is the ONLY dimension that scales multiplicatively (product x
	fabric x sleeve x size = a manageable few hundred rows in practice,
	not the ~128,000 that a full 7-dimension exact-match table would need).
	Collar/Stitching/Sublimation are priced separately as additive
	surcharges (see P3Surcharge) precisely to avoid that explosion - most
	collar/stitching/sublimation choices don't actually change cost, and
	forcing them into this table would mean pricing every combination
	whether or not it matters.
	"""

	def validate(self):
		if self.rate is not None and self.rate < 0:
			frappe.throw(_("Rate cannot be negative."))
		self._check_duplicate()

	def _check_duplicate(self):
		existing = frappe.db.exists(
			"P3 Base Price",
			{
				"product_type": self.product_type,
				"fabric": self.fabric,
				"sleeve_type": self.sleeve_type,
				"size": self.size,
				"is_active": 1,
				"name": ["!=", self.name],
			},
		)
		if existing and self.is_active:
			frappe.throw(
				_(
					"An active Base Price already exists for this exact combination "
					"(Product Type + Fabric + Sleeve Type + Size): {0}. "
					"Deactivate it first, or edit it directly instead of creating a duplicate."
				).format(existing)
			)
