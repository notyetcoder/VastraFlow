import frappe
from frappe import _
from frappe.model.document import Document

from p3erp.apparel_core import pricing

ZONE_FIELDS = ["front_print", "back_print", "sleeve_print"]
ZONE_COLOUR_FIELDS = {
	"front_print": "front_colour",
	"back_print": "back_colour",
	"sleeve_print": "sleeve_colour",
}
ZONE_LABELS = {"front_print": "Front", "back_print": "Back", "sleeve_print": "Sleeves"}

# Maps the child table's per-size quantity columns to the Sleeve Type
# label used everywhere else (pricing, Sales Order line descriptions).
MATRIX_SLEEVE_COLUMNS = {
	"hs_qty": "Half Sleeve",
	"fs_qty": "Full Sleeve",
	"sl_qty": "Sleeveless",
}


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


class VastraFlow(Document):
	"""VastraFlow (VastraFlow) - a lightweight custom order-entry layer
	that IS a Sales Order under the hood. It never diverges from core
	Sales Order behaviour; it just adds the apparel-specific fields Sales
	Order doesn't have.

	Lifecycle:
	  Save    -> Draft, docstatus 0. No Sales Order touched.
	  Submit  -> docstatus 1. Every non-empty matrix cell (Size x Sleeve
	             Type) must resolve to a Base Price (see pricing.py -
	             tiered Customer > Product > Global lookup) or submit is
	             blocked, listing every missing combination at once -
	             unless the current user has the Account Manager role, in
	             which case a quick-entry dialog lets them define the
	             missing price inline. Creates a real (draft) Sales Order
	             with ONE line item PER matrix cell - never merged, even
	             if two cells share a rate - links it back via
	             `sales_order`.
	  "Create Sales Order" button (create_sales_order_from_book) -> submits
	             the linked Sales Order for real. That's it - no BOM/Work
	             Order step. If a Work Order is ever needed for a specific
	             order, create it manually from the Sales Order the normal
	             ERPNext way; this app doesn't auto-route to one.
	  Cancel  -> cascades: cancels the Sales Order if it was submitted,
	             deletes it if it was still a draft link with nothing else
	             built on top of it.

	Price is deliberately never a field on this DocType or shown anywhere
	on this form - see P3BasePrice / P3PriceAdjustment / pricing.py for
	why pricing lives in its own dedicated, Account-Manager-controlled
	system instead.
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

		missing = self.get_missing_price_cells()
		if missing:
			frappe.throw(
				_(
					"Cannot submit - no Base Price found for the following combination(s):"
					"<br><br>{0}<br><br>{1}"
				).format(
					"<br>".join(missing),
					_("Ask an Account Manager to add a Base Price, or use the "
					  "\"Add Pricing\" option on this order if you have that role.")
					if "Account Manager" not in frappe.get_roles()
					else _("Use the \"Add Pricing\" button on this order to define it now."),
				)
			)

	def on_submit(self):
		if not self.sales_order:
			so = self.create_linked_sales_order()
			self.db_set("sales_order", so.name)
			self.db_set("sales_order_status", "Draft")

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

	# -- matrix / validation helpers ----------------------------------

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

		Product Type isn't a variant - it's a plain Item - so its full
		name is just item_name directly (e.g. "Hoodies" instead of "HOO").
		"""
		self.fabric_label = self._variant_attribute_value(self.fabric, "Fabric")
		self.collar_label = self._variant_attribute_value(self.collar_type, "Collar Type")
		self.collar_image = (
			frappe.db.get_value("Item", self.collar_type, "image") if self.collar_type else ""
		)
		self.product_type_label = (
			frappe.db.get_value("Item", self.product_type, "item_name") if self.product_type else ""
		)

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

	def iter_matrix_cells(self):
		"""Yield (size_code, sleeve_type_label, qty) for every non-zero cell
		in the matrix. This is the single source of truth for "what counts
		as a cell" - used identically by the before_submit price check and
		by create_linked_sales_order()'s line-item loop, so the two can
		never drift out of sync with each other.
		"""
		for row in self.get("size_matrix") or []:
			for column, sleeve_type in MATRIX_SLEEVE_COLUMNS.items():
				qty = row.get(column) or 0
				if qty > 0:
					yield row.size_code, sleeve_type, qty

	# -- pricing --------------------------------------------------------

	def spec_values_for(self, size_code, sleeve_type):
		"""The order's actual value for each possible price-adjustment
		attribute, for a specific matrix cell. Sublimation/Collar/
		Stitching/etc are fixed for the whole order; Size and Sleeve Type
		vary per cell.
		"""
		return {
			"Sublimation": self.sublimation_type if self.sublimation_type != "None" else None,
			"Size": size_code,
			"Sleeve Type": sleeve_type,
			"Collar Type": self.collar_label,
			"Stitching Type": self.stitching,
			# Button/Thread Color/Packaging/Label/Neck Tape: no matching
			# fields exist on this form yet - left out until they do.
			# Adding a field later automatically starts contributing here
			# once both the field exists AND its toggle is switched on.
		}

	def price_cell(self, size_code, sleeve_type):
		"""Full pricing.calculate_price() result for one matrix cell."""
		return pricing.calculate_price(
			fabric=self.fabric,
			product_type=self.product_type,
			customer=self.customer,
			spec_values=self.spec_values_for(size_code, sleeve_type),
		)

	def get_missing_price_cells(self):
		"""All (sleeve+size) combinations in the matrix with no resolvable
		Base Price. Collected all at once rather than stopping at the
		first miss.
		"""
		missing = []
		for size_code, sleeve_type, qty in self.iter_matrix_cells():
			result = self.price_cell(size_code, sleeve_type)
			if result["missing_base_price"]:
				missing.append(f"Fabric '{self.fabric_label or self.fabric}' + {sleeve_type} + Size {size_code}")
		return missing

	def spec_summary(self, size_code=None, sleeve_type=None):
		"""One-line human summary of the garment spec, used as each Sales
		Order line's description - this is what keeps multiple lines
		sharing the same Item code visually distinguishable from each
		other, since every matrix cell becomes its own separate line.
		"""
		parts = []
		if sleeve_type:
			parts.append(sleeve_type)
		if size_code:
			parts.append(f"Size {size_code}")
		if self.fabric_label:
			parts.append(f"Fabric: {self.fabric_label}")
		if self.collar_label:
			parts.append(f"Collar: {self.collar_label}")
		if self.sublimation_type and self.sublimation_type != "None":
			parts.append(f"Sublimation: {self.sublimation_type}")
		if self.collar_colour:
			parts.append(f"Collar Colour: {self.collar_colour}")
		if self.border_colour:
			parts.append(f"Border Colour: {self.border_colour}")
		return " | ".join(parts)

	def get_default_company(self):
		"""Programmatic frappe.get_doc({...}).insert() does NOT get the
		client-side 'New Document' defaulting that fills in Company when
		you open a fresh Sales Order in the Desk UI - it has to be
		resolved explicitly here, or Sales Order submission fails with
		'Company is mandatory'.
		"""
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
		if not company:
			frappe.throw(
				_(
					"No default Company is configured (neither for your user nor as a Global "
					"Default) - Sales Order cannot be created without one. Set a default Company "
					"in your User settings or under Global Defaults."
				)
			)
		return company

	def create_linked_sales_order(self):
		"""One Sales Order line item per matrix cell - never merged, even
		when two cells resolve to an identical rate (confirmed explicitly:
		every variant gets its own line).
		"""
		items = []
		currency = None

		for size_code, sleeve_type, qty in self.iter_matrix_cells():
			result = self.price_cell(size_code, sleeve_type)
			if result["missing_base_price"]:
				# Should never happen - before_submit already checked this -
				# but never silently price something at 0 if it somehow does.
				frappe.throw(
					_("No Base Price found for {0}, Size {1}.").format(sleeve_type, size_code)
				)
			currency = currency or result["currency"]
			items.append(
				{
					"item_code": self.product_type,
					"qty": qty,
					"rate": result["total"],
					"delivery_date": self.delivery_date,
					"description": self.spec_summary(size_code, sleeve_type),
				}
			)

		if not items:
			frappe.throw(_("No priceable quantities found in the Size & Sleeve Matrix."))

		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": self.customer,
				"company": self.get_default_company(),
				"customer_address": self.customer_address,
				"contact_person": self.contact_person,
				"transaction_date": self.transaction_date,
				"delivery_date": self.delivery_date,
				"currency": currency or "INR",
				"items": items,
			}
		)
		so.insert(ignore_permissions=True)
		return so

	@frappe.whitelist()
	def create_sales_order_from_book(self):
		"""Called by the 'Create Sales Order' button. Submits the Sales
		Order that was already created (as a draft) when this document was
		submitted. No BOM/Work Order step - if production needs a Work
		Order for a given order, create it manually from the Sales Order
		the normal ERPNext way.
		"""
		if self.docstatus != 1:
			frappe.throw(_("Submit this VastraFlow first."))

		if not self.sales_order:
			frappe.throw(_("No linked Sales Order was found - this shouldn't happen post-submit."))

		so = frappe.get_doc("Sales Order", self.sales_order)

		if so.docstatus == 1:
			frappe.msgprint(_("Sales Order {0} is already submitted.").format(so.name))
			return {"sales_order": so.name, "status": "already_submitted"}

		so.submit()
		self.db_set("sales_order_status", "Submitted")
		return {"sales_order": so.name, "status": "submitted"}

	@frappe.whitelist()
	def get_missing_price_prefill(self):
		"""Account-Manager-only helper for the "Add Pricing" quick-entry
		flow: returns field values for the FIRST unpriced matrix cell,
		pre-formatted to seed a new P3 Base Price quick-entry dialog,
		scoped to this order's exact Product Type (the narrowest, safest
		starting tier - the Account Manager can clear Product Type before
		saving to make it a Global rate instead if that's more useful).
		"""
		if "Account Manager" not in frappe.get_roles():
			frappe.throw(_("Only an Account Manager can add pricing."))

		for size_code, sleeve_type, qty in self.iter_matrix_cells():
			result = self.price_cell(size_code, sleeve_type)
			if result["missing_base_price"]:
				return {
					"fabric": self.fabric,
					"product_type": self.product_type,
					"rule_name": f"{self.product_type_label or self.product_type} - {self.fabric_label or self.fabric}",
				}

		return None
