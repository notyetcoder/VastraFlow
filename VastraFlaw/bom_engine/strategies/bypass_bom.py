import frappe


class BypassBOMStrategy:
	"""Creates a Work Order directly, skipping multi-level BOM transfer.
	Best for direct sublimation/custom jobs with no formal raw-material
	tracking requirement.
	"""

	def __init__(self, spec_doc):
		self.doc = spec_doc

	def execute(self):
		wo = frappe.get_doc(
			{
				"doctype": "Work Order",
				"production_item": self.doc.product_type,
				"qty": self.doc.total_qty,
				"sales_order": self.doc.sales_order,
				"description": f"Direct Work Order via Bypass BOM for {self.doc.name}",
				"use_multi_level_bom": 0,
				"skip_transfer": 1,
			}
		)
		wo.insert(ignore_permissions=True)
		return {"action": "BYPASS_BOM", "work_order": wo.name}
