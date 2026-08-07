import frappe
from frappe import _
from frappe.model.document import Document


class P3BasePrice(Document):
	"""Fabric is always required; Product Type and Customer are both
	optional, and which ones are set determines which priority tier a row
	serves:

	  Customer + Product Type set  -> Customer-specific override for that
	                                   exact product (highest priority)
	  Customer set, Product blank  -> Customer-specific override across
	                                   any product
	  Product Type set, no Customer -> Product-specific rate (beats Global)
	  Neither set                  -> Global rate for this Fabric, applies
	                                   to any product/customer (lowest
	                                   priority, but the broadest fallback)

	See P3OrderBook.get_base_rate() for the actual lookup order. This one
	table serves all four tiers instead of needing four separate lists.
	"""

	def validate(self):
		if self.rate is not None and self.rate < 0:
			frappe.throw(_("Rate cannot be negative."))
		self._check_duplicate()

	def _check_duplicate(self):
		existing = frappe.db.exists(
			"P3 Base Price",
			{
				"fabric": self.fabric,
				# Frappe stores a blank Link field as '' (empty string),
				# not SQL NULL - filtering with None here would silently
				# never match, letting real duplicates slip through.
				"product_type": self.product_type or "",
				"customer": self.customer or "",
				"is_active": 1,
				"name": ["!=", self.name],
			},
		)
		if existing and self.is_active:
			frappe.throw(
				_(
					"An active Base Price already exists for this exact Fabric + Product Type + "
					"Customer combination: {0}. Deactivate it first, or edit it directly instead "
					"of creating a duplicate."
				).format(existing)
			)
