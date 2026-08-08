import frappe


def execute():
	"""Renames the DocType "VastraFlow" to "VastraFlow Order Book",
	preserving every existing order and its table data (this uses
	Frappe's real DocType rename path - it renames the DB table, updates
	the DocType/Module Def records, and fixes up any Link fields pointing
	at it elsewhere) - it does NOT create a fresh empty doctype.

	Runs in [pre_model_sync] (see patches.txt) so it executes BEFORE
	`bench migrate` syncs the new vastraflow_order_book.json - if this
	ran after, Frappe would just create "VastraFlow Order Book" fresh
	from that json with an empty table, orphaning all existing data under
	the old "VastraFlow" table instead of carrying it forward.
	"""
	old_name = "VastraFlow"
	new_name = "VastraFlow Order Book"

	if not frappe.db.exists("DocType", old_name):
		# Either a brand-new install (nothing to rename) or this patch
		# already ran - either way, nothing to do.
		return

	if frappe.db.exists("DocType", new_name):
		# Already renamed (e.g. patch re-run after a partial migrate) -
		# don't attempt it twice.
		return

	frappe.rename_doc("DocType", old_name, new_name, force=True, rebuild_search=False)
	frappe.reload_doctype(new_name, force=True)
	frappe.clear_cache(doctype=new_name)
