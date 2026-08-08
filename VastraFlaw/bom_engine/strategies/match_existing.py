import frappe
from frappe import _


class MatchExistingBOMStrategy:
	"""Finds an existing active BOM for the ordered item and links it to a
	new Work Order.
	"""

	def __init__(self, spec_doc):
		self.doc = spec_doc

	def execute(self):
		boms = frappe.get_all(
			"BOM",
			filters={"item": self.doc.product_type, "is_active": 1, "docstatus": 1},
			order_by="is_default desc, modified desc",
			limit=1,
		)

		if not boms:
			frappe.throw(
				_(
					"No active, submitted BOM was found for item '{0}'. Either create/submit "
					"a BOM for this item first, or change the BOM Routing Strategy on {1} to "
					"'Auto Create' or 'Bypass BOM'."
				).format(self.doc.product_type, self.doc.name)
			)

		bom_name = boms[0].name

		wo = frappe.get_doc(
			{
				"doctype": "Work Order",
				"production_item": self.doc.product_type,
				"bom_no": bom_name,
				"qty": self.doc.total_qty,
				"sales_order": self.doc.sales_order,
				"description": f"Matched BOM Work Order for {self.doc.name}",
			}
		)
		wo.insert(ignore_permissions=True)
		return {"action": "MATCH_EXISTING", "work_order": wo.name, "bom": bom_name}
