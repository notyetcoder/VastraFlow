import frappe
from frappe.model.document import Document


class VastraFlowPriceMatrix(Document):
	def validate(self):
		self._validate_rate()
		self._check_duplicate()

	def _validate_rate(self):
		if float(self.rate or 0) <= 0:
			frappe.throw(frappe._("Rate must be greater than zero."))

	def _check_duplicate(self):
		"""One submitted rate per product type + fabric + sublimation combination."""
		existing = frappe.db.get_value(
			"VastraFlow Price Matrix",
			{
				"product_type": self.product_type,
				"fabric": self.fabric,
				"sublimation_type": self.sublimation_type,
				"docstatus": 1,
				"name": ["!=", self.name],
			},
			"name",
		)
		if existing:
			frappe.throw(
				frappe._(
					"{0} already prices {1} + {2} + {3}. Cancel or amend that entry instead of "
					"creating a second one."
				).format(
					f"<a href='/app/vastraflow-price-matrix/{existing}'><b>{existing}</b></a>",
					self.product_type,
					self.fabric,
					self.sublimation_type,
				),
				title=frappe._("Duplicate Price"),
			)
