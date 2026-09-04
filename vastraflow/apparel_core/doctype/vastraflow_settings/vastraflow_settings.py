import frappe
from frappe.model.document import Document

from vastraflow.apparel_core.logging_utils import get_logger
from vastraflow.apparel_core.settings import sync_select_options


class VastraFlowSettings(Document):
	def validate(self):
		self._validate_sizes()
		self._validate_plain_option()

	def on_update(self):
		"""Push the configured dropdown lists onto the forms straight away."""
		try:
			sync_select_options(self)
		except Exception as exc:
			get_logger().error(f"Option sync failed: {exc}")
			frappe.log_error(frappe.get_traceback(), "VastraFlow: option sync")
			frappe.msgprint(
				frappe._("Settings saved, but the dropdowns could not be refreshed: {0}").format(exc),
				indicator="orange",
			)

	def _validate_sizes(self):
		if self.size_mode == "Custom List":
			labels = [(r.size_label or "").strip() for r in self.sizes or []]
			active = [label for label in labels if label]
			if not active:
				frappe.throw(frappe._("Add at least one size, or switch Size Mode to Numeric Range."))
			if len(set(active)) != len(active):
				frappe.throw(frappe._("Size labels must be unique."))
			return

		if int(self.size_step or 0) <= 0:
			frappe.throw(frappe._("Step must be greater than zero."))
		if int(self.size_end or 0) < int(self.size_start or 0):
			frappe.throw(frappe._("End Size cannot be smaller than Start Size."))

		span = (int(self.size_end) - int(self.size_start)) // int(self.size_step) + 1
		if span > 200:
			frappe.throw(
				frappe._("That range produces {0} sizes. Narrow it to 200 or fewer.").format(span)
			)

	def _validate_plain_option(self):
		"""The 'no artwork needed' value has to exist in the sublimation list."""
		if self.artwork_enforcement == "Ignore":
			return

		plain = (self.plain_option_value or "").strip()
		options = [(r.option_value or "").strip() for r in self.sublimation_options or []]
		if plain and options and plain not in options:
			frappe.msgprint(
				frappe._(
					"<b>{0}</b> is not one of the Sublimation Options, so every order will be "
					"treated as needing artwork."
				).format(plain),
				indicator="orange",
				title=frappe._("Check Plain Sublimation Value"),
			)
