import frappe
from frappe import _
from frappe.model.document import Document


class ApparelOrderSpec(Document):
	"""Controller for the Apparel Order Spec DocType.

	Server-side validation always recomputes totals from the child table
	(`size_matrix`) rather than trusting values sent by the client. The
	on-screen matrix grid (size_sleeve_html) is a UI convenience only;
	`size_matrix` is the actual data store and is what gets validated,
	saved, and later read by the BOM engine / print format.
	"""

	def validate(self):
		self.recalculate_matrix_totals()
		self.validate_matrix_has_quantity()

	def before_submit(self):
		self.recalculate_matrix_totals()
		self.validate_matrix_has_quantity()

		if not self.sales_order:
			frappe.throw(_("Sales Order is mandatory before submitting an Apparel Order Spec."))

		if not frappe.db.exists("Item", self.product_type):
			frappe.throw(_("Product Type {0} does not exist as an Item.").format(self.product_type))

	def recalculate_matrix_totals(self):
		"""Recompute each row's total and the document grand total.

		Never trust the qty math done in the browser - always recompute
		server-side so total_qty (which downstream Work Orders are
		created against) can't be tampered with or drift out of sync.
		"""
		grand_total = 0
		for row in self.get("size_matrix") or []:
			row.hs_qty = row.hs_qty or 0
			row.fs_qty = row.fs_qty or 0
			row.sl_qty = row.sl_qty or 0

			for fieldname in ("hs_qty", "fs_qty", "sl_qty"):
				if row.get(fieldname) < 0:
					frappe.throw(
						_("Row {0}: Quantities cannot be negative.").format(row.idx)
					)

			row.total_qty = row.hs_qty + row.fs_qty + row.sl_qty
			grand_total += row.total_qty

		self.total_qty = grand_total

	def validate_matrix_has_quantity(self):
		if not self.total_qty:
			frappe.throw(
				_("Please enter at least one quantity in the Size & Sleeve Matrix before saving.")
			)
