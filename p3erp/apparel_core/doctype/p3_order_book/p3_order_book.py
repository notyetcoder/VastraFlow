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

# Maps the child table's per-size quantity columns to the Sleeve Type label
# used everywhere else (P3 Base Price, P3 Surcharge matching, Sales Order
# line descriptions).
MATRIX_SLEEVE_COLUMNS = {
	"hs_qty": "Half Sleeve",
	"fs_qty": "Full Sleeve",
	"sl_qty": "Sleeveless",
}

SURCHARGE_DIMENSIONS = [
	# (P3O fieldname to read the resolved value from, "Applies To" value in P3 Surcharge)
	("collar_label", "Collar Type"),
	("stitching", "Stitching Type"),
	("sublimation_type", "Sublimation Type"),
]


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
	  Submit  -> docstatus 1. Every non-empty matrix cell (Size x Sleeve
	             Type) must resolve to an active P3 Base Price (blocked,
	             with every missing combination listed at once, otherwise).
	             Creates a real (draft) Sales Order with ONE line item PER
	             matrix cell - never merged, even if two cells share a
	             rate - each priced as base rate + any matching surcharges,
	             links it back via `sales_order`, then routes to the BOM
	             engine to create a Work Order against that real Sales
	             Order (at the whole-order total_qty level - the BOM engine
	             has no awareness of per-line pricing granularity).
	  "Create Sales Order" button (create_sales_order_from_book) -> submits
	             the linked Sales Order for real.
	  Cancel  -> cascades: cancels the Sales Order if it was submitted,
	             deletes it if it was still a draft link with nothing else
	             built on top of it.

	Price is deliberately never a field on this DocType or shown anywhere
	on this form - see P3BasePrice / P3Surcharge for why pricing lives in
	its own dedicated, management-controlled DocTypes instead.
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

		# Validate every cell has a resolvable base price BEFORE attempting
		# to build the Sales Order, and report every missing combination in
		# one message rather than making the user fix them one at a time.
		missing = []
		for size_code, sleeve_type, qty in self.iter_matrix_cells():
			try:
				self.get_base_rate(size_code, sleeve_type)
			except frappe.ValidationError:
				missing.append(f"Fabric '{self.fabric_label or self.fabric}' + {sleeve_type} + Size {size_code}")

		if missing:
			frappe.throw(
				_(
					"Cannot submit - no active Base Price found for the following combination(s):"
					"<br><br>{0}<br><br>Add them in <b>P3 Base Price</b> (or a customer-specific "
					"entry in <b>P3 Base Price Customer Override</b>) before submitting."
				).format("<br>".join(missing))
			)

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

	def get_base_rate(self, size_code, sleeve_type):
		"""Exact-match lookup only - no fallback, no partial matching.
		Customer-specific override list is checked first; the generic list
		second. Throws if neither has this exact combination.
		"""
		override = frappe.db.get_value(
			"P3 Base Price Customer Override",
			{
				"customer": self.customer,
				"product_type": self.product_type,
				"fabric": self.fabric,
				"sleeve_type": sleeve_type,
				"size": size_code,
				"is_active": 1,
			},
			["rate", "currency"],
			as_dict=True,
		)
		if override:
			return override

		generic = frappe.db.get_value(
			"P3 Base Price",
			{
				"product_type": self.product_type,
				"fabric": self.fabric,
				"sleeve_type": sleeve_type,
				"size": size_code,
				"is_active": 1,
			},
			["rate", "currency"],
			as_dict=True,
		)
		if generic:
			return generic

		frappe.throw(
			_("No Base Price found for Fabric '{0}' + {1} + Size {2}.").format(
				self.fabric_label or self.fabric, sleeve_type, size_code
			)
		)

	def get_surcharge_total(self):
		"""Sum of all matching surcharges for this order's fixed spec
		(Collar/Stitching/Sublimation - these don't vary per matrix cell,
		they're set once on the P3O header). A missing surcharge row is
		NOT an error - it's treated as zero, since most spec values don't
		actually change cost.
		"""
		total = 0
		for source_field, applies_to in SURCHARGE_DIMENSIONS:
			value = self.get(source_field)
			if not value or (source_field == "sublimation_type" and value == "None"):
				continue
			amount = frappe.db.get_value(
				"P3 Surcharge",
				{
					"product_type": self.product_type,
					"applies_to": applies_to,
					"spec_value": value,
					"is_active": 1,
				},
				"amount",
			)
			total += amount or 0
		return total

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

	def create_linked_sales_order(self):
		"""One Sales Order line item per matrix cell - never merged, even
		when two cells resolve to an identical rate (confirmed explicitly:
		every variant gets its own line). Each line's rate = base rate +
		surcharge total (surcharges are the same for every line on this
		order, since Collar/Stitching/Sublimation are fixed per order, not
		per cell).
		"""
		surcharge_total = self.get_surcharge_total()
		items = []
		currency = None

		for size_code, sleeve_type, qty in self.iter_matrix_cells():
			base = self.get_base_rate(size_code, sleeve_type)
			currency = currency or base.currency
			items.append(
				{
					"item_code": self.product_type,
					"qty": qty,
					"rate": (base.rate or 0) + surcharge_total,
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
