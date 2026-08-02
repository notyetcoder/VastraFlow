import frappe
from frappe import _


class AutoGenerateBOMStrategy:
	"""Programmatically creates a new BOM for a custom product variation,
	then creates a Work Order against it.

	IMPORTANT: A BOM with zero item rows is not just "empty" - Frappe will
	either reject it outright or (if it slips through) produce a Work
	Order that thinks it needs to consume nothing, which silently breaks
	stock/material transfer on the shop floor. The previous implementation
	always inserted `items: []`, so every Auto-Generated BOM was
	non-functional. Since P3 Order Book doesn't capture a raw
	material list directly, this strategy clones the item list from the
	most recently modified existing BOM for the same product as a
	starting template, and refuses to proceed if none exists - a loud,
	explicit failure is far safer than a silently broken BOM.
	"""

	def __init__(self, spec_doc):
		self.doc = spec_doc

	def execute(self):
		template_items = self._get_template_items()

		bom = frappe.get_doc(
			{
				"doctype": "BOM",
				"item": self.doc.product_type,
				"quantity": 1,
				"is_active": 1,
				"is_default": 0,
				"items": template_items,
			}
		)
		bom.insert(ignore_permissions=True)
		bom.submit()

		wo = frappe.get_doc(
			{
				"doctype": "Work Order",
				"production_item": self.doc.product_type,
				"bom_no": bom.name,
				"qty": self.doc.total_qty,
				"sales_order": self.doc.sales_order,
				"description": f"Auto Generated BOM Work Order for {self.doc.name}",
			}
		)
		wo.insert(ignore_permissions=True)
		return {"action": "AUTO_CREATE", "work_order": wo.name, "bom": bom.name}

	def _get_template_items(self):
		source_bom = frappe.get_all(
			"BOM",
			filters={"item": self.doc.product_type},
			order_by="modified desc",
			limit=1,
		)

		if not source_bom:
			frappe.throw(
				_(
					"'Auto Create' cannot build a raw-material BOM for '{0}' because no prior "
					"BOM exists for this item to use as a template. Create an initial BOM for "
					"this item once (even a draft), or use 'Match Existing' / 'Bypass BOM' "
					"instead."
				).format(self.doc.product_type)
			)

		source = frappe.get_doc("BOM", source_bom[0].name)
		return [
			{
				"item_code": row.item_code,
				"qty": row.qty,
				"uom": row.uom,
				"rate": row.rate,
			}
			for row in source.items
		]
