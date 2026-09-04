import frappe
from frappe.model.document import Document


class VastraFlowBOMRule(Document):
	def validate(self):
		if float(self.fabric_qty_per_unit or 0) <= 0:
			frappe.throw(frappe._("Fabric Qty per Garment must be greater than zero."))

		if not self.use_order_fabric and not self.fixed_fabric_item:
			frappe.throw(
				frappe._("Either use the fabric from the order, or choose a Fixed Fabric Item.")
			)

		if self.include_collar and float(self.collar_qty_per_unit or 0) <= 0:
			self.collar_qty_per_unit = 1

		self._validate_components()

	def _validate_components(self):
		seen = set()
		for row in self.components or []:
			if float(row.qty_per_unit or 0) <= 0:
				frappe.throw(
					frappe._("Row {0}: component quantity must be greater than zero.").format(row.idx)
				)

			key = (row.item_code, row.apply_if_sleeve or "All")
			if key in seen:
				frappe.throw(
					frappe._("Row {0}: {1} is listed twice for the same sleeve type.").format(
						row.idx, row.item_code
					)
				)
			seen.add(key)

			if row.item_code == self.product_type:
				frappe.throw(
					frappe._("Row {0}: a garment cannot consume itself as a component.").format(row.idx)
				)
