import frappe
from frappe import _
from frappe.model.document import Document


class P3PriceList(Document):
	"""The entire pricing model, deliberately simple: Fabric x Sublimation
	Type -> Rate. Nothing else affects price - Collar, Stitching, Size,
	Sleeve, Buttons etc. are production specs only.

	Sublimation Type is NOT a hardcoded option list - see
	p3_price_list.js, which populates it at runtime from the real
	"Sublimation" Item Attribute (the same source of truth the Order Book
	itself uses for its Sublimation Type field). Renaming or adding a
	value in that Item Attribute is all that's needed for it to show up
	here too - no code change required.
	"""

	def validate(self):
		self._resolve_fabric_label()
		self._check_rate()
		self._check_duplicate()

	def _resolve_fabric_label(self):
		self.fabric_label = (
			frappe.db.get_value("Item", self.fabric, "item_name") if self.fabric else ""
		)

	def _check_rate(self):
		if self.rate is not None and self.rate < 0:
			frappe.throw(_("Rate cannot be negative."))

	def _check_duplicate(self):
		existing = frappe.db.exists(
			"P3 Price List",
			{
				"fabric": self.fabric,
				"sublimation_type": self.sublimation_type,
				"is_active": 1,
				"name": ["!=", self.name],
			},
		)
		if existing and self.is_active:
			frappe.throw(
				_(
					"An active price already exists for {0} + {1}: {2}. Deactivate it first, "
					"or edit it directly instead of creating a duplicate."
				).format(self.fabric_label or self.fabric, self.sublimation_type, existing)
			)
