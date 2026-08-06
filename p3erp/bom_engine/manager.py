import frappe
from frappe import _

# BypassBOMStrategy is intentionally NOT imported/registered below - it's
# disabled, not deleted (the file is still at
# bom_engine/strategies/bypass_bom.py for future use). Reasoning: if an
# order genuinely needs no BOM/Work Order at all, that's just "don't
# create a Work Order, go straight to Sales Invoice" - which doesn't need
# a dedicated strategy class to achieve. Re-enable by importing it again
# and adding it back to STRATEGY_MAP below.
from p3erp.bom_engine.strategies.match_existing import MatchExistingBOMStrategy
from p3erp.bom_engine.strategies.auto_generate import AutoGenerateBOMStrategy


class BOMDecisionEngine:
	"""Strategy dispatcher that routes a submitted P3 Order Book to the
	correct Work Order creation strategy based on doc.bom_strategy.

	Called from P3OrderBook.create_sales_order_from_book() - deliberately
	AFTER the linked Sales Order has been submitted (docstatus=1), not at
	P3O's own on_submit(). ERPNext's own Work Order.validate_sales_order()
	requires the linked Sales Order to already be submitted; calling this
	any earlier (against a still-draft Sales Order) fails with "Sales
	Order X is not valid" - a real bug hit and fixed once already.
	"""

	STRATEGY_MAP = {
		"MATCH_EXISTING": MatchExistingBOMStrategy,
		"AUTO_CREATE": AutoGenerateBOMStrategy,
	}

	@classmethod
	def process_apparel_order(cls, doc, method=None):
		policy = doc.bom_strategy or "MATCH_EXISTING"
		strategy_class = cls.STRATEGY_MAP.get(policy)

		if not strategy_class:
			frappe.throw(
				_("Unknown BOM Routing Strategy '{0}'. Valid options are: {1}").format(
					policy, ", ".join(cls.STRATEGY_MAP.keys())
				)
			)

		if not doc.sales_order:
			frappe.throw(_("Cannot create a Work Order: Sales Order is missing on {0}.").format(doc.name))

		if not frappe.db.get_value("Sales Order", doc.sales_order, "docstatus") == 1:
			frappe.throw(
				_(
					"Cannot create a Work Order: Sales Order {0} must be submitted first."
				).format(doc.sales_order)
			)

		if not doc.product_type or not frappe.db.exists("Item", doc.product_type):
			frappe.throw(
				_("Cannot create a Work Order: Product Type '{0}' is missing or does not exist.").format(
					doc.product_type
				)
			)

		if not doc.total_qty:
			frappe.throw(_("Cannot create a Work Order: Total Quantity is zero on {0}.").format(doc.name))

		instance = strategy_class(doc)

		try:
			result = instance.execute()
		except frappe.ValidationError:
			# Strategy already raised a clear, user-facing message - just
			# let it propagate. Frappe's request wrapper will roll back
			# any partially-created docs (e.g. an inserted BOM before a
			# failing Work Order insert) - and, since this now runs after
			# so.submit(), that rollback also correctly undoes the Sales
			# Order submission itself, keeping the two atomic together.
			raise
		except Exception:
			frappe.log_error(
				title=f"BOM Routing failed for {doc.name} (strategy: {policy})",
				message=frappe.get_traceback(),
			)
			frappe.throw(
				_(
					"Failed to route {0} via the '{1}' strategy. The submission has been "
					"rolled back and no Work Order was created. See Error Log for details."
				).format(doc.name, policy)
			)
			return

		frappe.msgprint(
			_("P3 Order Book {0}: Work Order routed via {1} (WO ID: {2})").format(
				doc.name, policy, result.get("work_order")
			)
		)
