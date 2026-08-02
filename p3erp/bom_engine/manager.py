import frappe
from frappe import _

from p3erp.bom_engine.strategies.bypass_bom import BypassBOMStrategy
from p3erp.bom_engine.strategies.match_existing import MatchExistingBOMStrategy
from p3erp.bom_engine.strategies.auto_generate import AutoGenerateBOMStrategy


class BOMDecisionEngine:
	"""Strategy dispatcher that routes a submitted P3 Order Book to the
	correct Work Order creation strategy based on doc.bom_strategy.

	Called directly from P3OrderBook.on_submit() (not via hooks.py
	doc_events) after the linked Sales Order has already been created, so
	doc.sales_order is guaranteed to be set by the time this runs.
	"""

	STRATEGY_MAP = {
		"MATCH_EXISTING": MatchExistingBOMStrategy,
		"AUTO_CREATE": AutoGenerateBOMStrategy,
		"BYPASS_BOM": BypassBOMStrategy,
	}

	@classmethod
	def process_apparel_order(cls, doc, method=None):
		policy = doc.bom_strategy or "BYPASS_BOM"
		strategy_class = cls.STRATEGY_MAP.get(policy)

		if not strategy_class:
			frappe.throw(
				_("Unknown BOM Routing Strategy '{0}'. Valid options are: {1}").format(
					policy, ", ".join(cls.STRATEGY_MAP.keys())
				)
			)

		if not doc.sales_order:
			frappe.throw(_("Cannot create a Work Order: Sales Order is missing on {0}.").format(doc.name))

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
			# failing Work Order insert) since we never call
			# frappe.db.commit() ourselves here or in the strategies.
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
			_("Apparel Spec {0}: Work Order routed via {1} (WO ID: {2})").format(
				doc.name, policy, result.get("work_order")
			)
		)
