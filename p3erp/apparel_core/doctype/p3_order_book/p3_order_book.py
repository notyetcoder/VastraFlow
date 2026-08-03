import frappe
from frappe import _
from frappe.model.document import Document

ZONE_FIELDS = ["front_print", "back_print", "sleeve_print"]
ZONE_COLOUR_FIELDS = {
	"front_print": "front_colour",
	"back_print": "back_colour",
	"sleeve_print": "sleeve_colour",
}
ZONE_LABELS = {"front_print": "Front", "back_print": "Back", "sleeve_print": "Sleeves"}


def _locked_zones_for(sublimation_type):
	"""Which zones must be 'Sublimation' for a given Sublimation Type value.

	Matched by keyword rather than exact string equality, since the real
	Item Attribute values in ERPNext have inconsistent casing/spacing
	("Full sublimation" vs "Front & Back sublimation" vs whatever gets
	typed in next) - substring matching on 'full' / 'front' / 'back' is
	robust to that without needing the app and the ERPNext data to be
	kept in exact lockstep.
	"""
	value = (sublimation_type or "").lower()

	if "full" in value:
		return ["front_print", "back_print", "sleeve_print"]
	if "front" in value and "back" in value:
		return ["front_print", "back_print"]
	if "front" in value:
		return ["front_print"]
	if "back" in value:
		return ["back_print"]
	return []


class P3OrderBook(Document):
	"""P3 Order Book - a lightweight custom order-entry layer that IS a
	Sales Order under the hood. It never diverges from core Sales Order
	behaviour; it just adds the apparel-specific fields Sales Order doesn't
	have. See module docstring in bom_engine/manager.py for the routing
	side of this flow.

	Lifecycle:
	  Save    -> Draft, docstatus 0. No Sales Order touched.
	  Submit  -> docstatus 1. Requires an active P3 Item Price List entry
	             for the chosen Product Type (blocked otherwise). Creates a
	             real (draft) Sales Order priced from that list, links it
	             back via `sales_order`, then routes to the BOM engine to
	             create a Work Order against that real Sales Order.
	  "Create Sales Order" button (create_sales_order_from_book) -> submits
	             the linked Sales Order for real.
	  Cancel  -> cascades: cancels the Sales Order if it was submitted,
	             deletes it if it was still a draft link with nothing else
	             built on top of it.

	Price is deliberately never a field on this DocType or shown anywhere
	on this form - see P3ItemPriceList for why.
	"""

	def validate(self):
		self.recalculate_matrix_totals()
		self.validate_matrix_has_quantity()
		self.validate_dates()
		self.validate_sublimation_zones()
		self.refresh_sales_order_status()
		self.resolve_variant_labels()

	def before_submit(self):
		if not frappe.db.exists("Item", self.product_type):
			frappe.throw(_("Product Type {0} does not exist as an Item.").format(self.product_type))

		self.get_active_price(self.product_type)

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
		"""Enforce the Front/Back/Sleeve sublimation matrix - see
		_locked_zones_for() docstring for the exact rule and why it's
		keyword-matched rather than exact-string-matched.

		"free" zones = Solid Color / Logo / A4 (never Sublimation - only a
		locked zone may be Sublimation). Solid Color on any zone makes
		that zone's colour field mandatory.
		"""
		locked = _locked_zones_for(self.sublimation_type)

		for zone in ZONE_FIELDS:
			value = self.get(zone)

			if zone in locked:
				# Force the locked value server-side too - never trust the
				# client to have kept it in sync.
				self.set(zone, "Sublimation")
				continue

			if value == "Sublimation":
				frappe.throw(
					_(
						"{0} cannot be set to 'Sublimation' unless Sublimation Type locks that zone. "
						"Choose Solid Color, Logo, or A4 instead."
					).format(ZONE_LABELS[zone])
				)

			if value == "Solid Color":
				colour_field = ZONE_COLOUR_FIELDS[zone]
				if not self.get(colour_field):
					frappe.throw(
						_("{0} is set to Solid Color - please choose a {1}.").format(
							ZONE_LABELS[zone], self.meta.get_label(colour_field)
						)
					)

	def refresh_sales_order_status(self):
		if self.sales_order and frappe.db.exists("Sales Order", self.sales_order):
			self.sales_order_status = frappe.db.get_value("Sales Order", self.sales_order, "docstatus")
			self.sales_order_status = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(
				self.sales_order_status, ""
			)

	def resolve_variant_labels(self):
		"""Fabric/Collar Type are Links to Item variants, whose item_name
		often isn't a friendly label (it may just repeat the item code,
		e.g. "Fabric-CM"). Pull the real attribute_value straight off the
		Item's own variant attributes instead - this is the actual
		human-readable name ("Soft Micro", "Round Neck") regardless of
		what the item_name/item_code happen to be, and needs no data
		cleanup on the ERPNext side to work.
		"""
		self.fabric_label = self._variant_attribute_value(self.fabric, "Fabric")
		self.collar_label = self._variant_attribute_value(self.collar_type, "Collar Type")

	@staticmethod
	def _variant_attribute_value(item_code, attribute_name):
		if not item_code or not frappe.db.exists("Item", item_code):
			return ""
		attrs = frappe.get_all(
			"Item Variant Attribute",
			filters={"parent": item_code, "attribute": attribute_name},
			fields=["attribute_value"],
			limit=1,
		)
		return attrs[0].attribute_value if attrs else ""

	def get_active_price(self, product_type):
		price = frappe.db.get_value(
			"P3 Item Price List",
			{"product_type": product_type, "is_active": 1},
			["rate", "currency"],
			as_dict=True,
		)
		if not price or price.rate in (None, 0):
			frappe.throw(
				_(
					"No active price is defined for Product Type '{0}'. Add one in "
					"<b>P3 Item Price List</b> before this order can be submitted."
				).format(product_type)
			)
		return price

	def spec_summary(self):
		"""One-line human summary of the garment spec, used as the Sales
		Order item row's description - useful in general, and specifically
		what keeps two Sales Orders for the same base Item (e.g. two
		different "Hoodies" specs) visually distinguishable from each
		other, since ERPNext doesn't otherwise show a diff between rows
		beyond the item_code.
		"""
		parts = []
		if self.fabric_label:
			parts.append(f"Fabric: {self.fabric_label}")
		if self.collar_label:
			parts.append(f"Collar: {self.collar_label}")
		if self.sublimation_type and self.sublimation_type != "None":
			parts.append(f"Sublimation: {self.sublimation_type}")
		return " | ".join(parts)

	def create_linked_sales_order(self):
		price = self.get_active_price(self.product_type)

		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": self.customer,
				"customer_address": self.customer_address,
				"contact_person": self.contact_person,
				"transaction_date": self.transaction_date,
				"delivery_date": self.delivery_date,
				"currency": price.currency,
				"items": [
					{
						"item_code": self.product_type,
						"qty": self.total_qty,
						"rate": price.rate,
						"delivery_date": self.delivery_date,
						"description": self.spec_summary() or None,
					}
				],
			}
		)
		so.insert(ignore_permissions=True)
		return so

	@frappe.whitelist()
	def create_sales_order_from_book(self):
		"""Called by the 'Create Sales Order' button. Submits the Sales
		Order that was already created (as a draft) when this document was
		submitted.
		"""
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
