import frappe
from frappe import _
from frappe.model.document import Document

LOCKED_ZONES = {
	"None": [],
	"Front Sublimation": ["front_print"],
	"Back Sublimation": ["back_print"],
	"Front & Back Sublimation": ["front_print", "back_print"],
	"Full Sublimation": ["front_print", "back_print", "sleeve_print"],
}

ZONE_FIELDS = ["front_print", "back_print", "sleeve_print"]
ZONE_COLOUR_FIELDS = {
	"front_print": "front_colour",
	"back_print": "back_colour",
	"sleeve_print": "sleeve_colour",
}


class P3OrderBook(Document):
	def validate(self):
		self.recalculate_matrix_totals()
		self.validate_matrix_has_quantity()
		self.validate_dates()
		self.validate_sublimation_zones()
		self.refresh_sales_order_status()

	def before_submit(self):
		if not frappe.db.exists("Item", self.product_type):
			frappe.throw(_("Product Type {0} does not exist as an Item.").format(self.product_type))

	def on_submit(self):
		if not self.sales_order:
			so = self.create_linked_sales_order()
			self.db_set("sales_order", so.name)
			self.db_set("sales_order_status", "Draft")

		from p3erp.bom_engine.manager import BOMDecisionEngine

		BOMDecisionEngine.process_apparel_order(self)

	def on_cancel(self):
		if not self.sales_order:
			return

		if not frappe.db.exists("Sales Order", self.sales_order):
			return

		so = frappe.get_doc("Sales Order", self.sales_order)

		if so.docstatus == 1:
			so.cancel()
		elif so.docstatus == 0:
			frappe.delete_doc("Sales Order", so.name, ignore_permissions=True)

	# -- helpers -----------------------------------------------------

	def recalculate_matrix_totals(self):
		grand_total = 0
		for row in self.get("size_matrix") or []:
			row.hs_qty = row.hs_qty or 0
			row.fs_qty = row.fs_qty or 0
			row.sl_qty = row.sl_qty or 0

			for fieldname in ("hs_qty", "fs_qty", "sl_qty"):
				if row.get(fieldname) < 0:
					frappe.throw(_("Row {0}: Quantities cannot be negative.").format(row.idx))

			row.total_qty = row.hs_qty + row.fs_qty + row.sl_qty
			grand_total += row.total_qty

		self.total_qty = grand_total

	def validate_matrix_has_quantity(self):
		if not self.total_qty:
			frappe.throw(_("Please enter at least one quantity in the Size & Sleeve Matrix before saving."))

	def validate_dates(self):
		if self.delivery_date and self.transaction_date and self.delivery_date < self.transaction_date:
			frappe.throw(_("Delivery Date cannot be before Order Date."))

	def validate_sublimation_zones(self):
		locked = LOCKED_ZONES.get(self.sublimation_type, [])

		for zone in ZONE_FIELDS:
			value = self.get(zone)

			if zone in locked:
				self.set(zone, "Sublimation")
				continue

			if value == "Sublimation":
				frappe.throw(
					_(
						"{0} cannot be set to 'Sublimation' unless Sublimation Type is '{0} Sublimation' "
						"(or Full Sublimation). Choose Solid Color, Logo, or A4 instead."
					).format(self._zone_label(zone))
				)

			if value == "Solid Color":
				colour_field = ZONE_COLOUR_FIELDS[zone]
				if not self.get(colour_field):
					frappe.throw(
						_("{0} is set to Solid Color - please choose a {1}.").format(
							self._zone_label(zone), self.meta.get_label(colour_field)
						)
					)

	@staticmethod
	def _zone_label(fieldname):
		return {"front_print": "Front", "back_print": "Back", "sleeve_print": "Sleeves"}[fieldname]

	def refresh_sales_order_status(self):
		if self.sales_order and frappe.db.exists("Sales Order", self.sales_order):
			status = frappe.db.get_value("Sales Order", self.sales_order, "docstatus")
			self.sales_order_status = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(status, "")

	def create_linked_sales_order(self):
		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": self.customer,
				"customer_address": self.customer_address,
				"contact_person": self.contact_person,
				"transaction_date": self.transaction_date,
				"delivery_date": self.delivery_date,
				"items": [
					{
						"item_code": self.product_type,
						"qty": self.total_qty,
						"delivery_date": self.delivery_date,
					}
				],
			}
		)
		so.insert(ignore_permissions=True)
		return so

	@frappe.whitelist()
	def create_sales_order_from_book(self):
		if self.docstatus != 1:
			frappe.throw(_("Submit this P3 Order Book first."))

		if not self.sales_order:
			frappe.throw(_("No linked Sales Order was found - this shouldn't happen post-submit."))

		so = frappe.get_doc("Sales Order", self.sales_order)

		if so.docstatus == 1:
			frappe.msgprint(_("Sales Order {0} is already submitted.").format(so.name))
			return {"sales_order": so.name, "status": "already_submitted"}

		so.submit()
		self.db_set("sales_order_status", "Submitted")
		return {"sales_order": so.name, "status": "submitted"}