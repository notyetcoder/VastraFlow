import frappe
from frappe import _
from frappe.model.document import Document


class P3BasePriceCustomerOverride(Document):
	"""Customer-specific base rate override. Checked BEFORE P3 Base Price
	whenever pricing an order line - see P3OrderBook.get_base_rate(). Same
	exact-match discipline as P3 Base Price, with Customer added as an
	eighth, always-mandatory matching field. No priority/specificity logic
	within this list itself - just two clearly ordered lists checked in a
	fixed sequence (customer-specific first, generic second).
	"""

	def validate(self):
		if self.rate is not None and self.rate < 0:
			frappe.throw(_("Rate cannot be negative."))
		self._check_duplicate()

	def _check_duplicate(self):
		existing = frappe.db.exists(
			"P3 Base Price Customer Override",
			{
				"customer": self.customer,
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
					"An active override already exists for this exact Customer + combination: {0}. "
					"Deactivate it first, or edit it directly instead of creating a duplicate."
				).format(existing)
			)
