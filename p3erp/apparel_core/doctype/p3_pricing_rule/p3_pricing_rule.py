import frappe
from frappe import _
from frappe.model.document import Document

MATCH_FIELDS = [
	"product_type", "fabric", "collar_type", "sleeve_type",
	"size", "stitching", "sublimation_type", "customer",
]


class P3PricingRule(Document):
	"""A single pricing rule. Which of the eight possible matching
	parameters actually apply to THIS rule is decided per-rule via its
	own `<field>_mandatory` checkboxes - a rule with only Fabric and
	Sublimation Type ticked mandatory matches ANY order with that
	fabric+sublimation combination, regardless of sleeve/size/etc.

	Multiple active rules CAN legitimately overlap and both match the
	same order (that's expected, not an error) - Priority decides which
	one wins; ties go to whichever was modified most recently. See
	P3OrderBook.find_matching_pricing_rule().
	"""

	def validate(self):
		if self.rate is not None and self.rate < 0:
			frappe.throw(_("Rate cannot be negative."))

		if not any(self.get(f"{field}_mandatory") for field in MATCH_FIELDS):
			frappe.throw(
				_(
					"At least one parameter must be ticked \u2018Mandatory\u2019 - a rule with none "
					"selected would match every single order, which is almost certainly not intended."
				)
			)

		for field in MATCH_FIELDS:
			if self.get(f"{field}_mandatory") and not self.get(field):
				frappe.throw(
					_("{0} is marked Mandatory but has no value set.").format(self.meta.get_label(field))
				)
