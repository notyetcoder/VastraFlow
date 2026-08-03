import frappe
from frappe import _
from frappe.model.document import Document


class P3ItemPriceList(Document):
	"""One active rate per Product Type. Kept as its own DocType -
	deliberately never surfaced on the P3 Order Book form itself - so
	price stays a management-controlled, centrally-defined list rather
	than something order-taking staff pick per order. P3OrderBook looks
	this up at submit time to price the auto-created Sales Order.
	"""

	def validate(self):
		if self.rate is not None and self.rate < 0:
			frappe.throw(_("Rate cannot be negative."))
