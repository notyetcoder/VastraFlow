app_name = "vastraflow"
app_title = "VastraFlow"
app_publisher = "VastraFlow"
app_description = "Garment order entry, matrix pricing, automatic BOM and production specs for ERPNext"
app_email = "dharani@spiceprofile.com"
app_license = "mit"

required_apps = ["erpnext"]

# Client scripts, loaded only on the forms that need them.
doctype_js = {
	"Sales Order": "public/js/sales_order.js",
}

app_include_css = "/assets/vastraflow/css/vastraflow.css"

# Print-format-only helpers - see apparel_core/print_helpers.py.
jinja = {
	"methods": [
		"vastraflow.apparel_core.print_helpers.get_collar_visual",
		"vastraflow.apparel_core.print_helpers.stitching_icon",
		"vastraflow.apparel_core.print_helpers.sleeve_icon",
		"vastraflow.apparel_core.print_helpers.button_icon",
		"vastraflow.apparel_core.print_helpers.collar_strip",
		"vastraflow.apparel_core.print_helpers.sleeve_strip",
		"vastraflow.apparel_core.print_helpers.item_display_name",
		"vastraflow.apparel_core.print_helpers.customer_block",
		"vastraflow.apparel_core.print_helpers.brand_mark",
	]
}

doc_events = {
	"Sales Order": {
		"before_validate": "vastraflow.apparel_core.doc_events.sales_order.before_validate",
		"validate": "vastraflow.apparel_core.doc_events.sales_order.validate",
		"before_submit": "vastraflow.apparel_core.doc_events.sales_order.before_submit",
		"on_submit": "vastraflow.apparel_core.doc_events.sales_order.on_submit",
		"on_update_after_submit": "vastraflow.apparel_core.doc_events.sales_order.on_update_after_submit",
		"before_cancel": "vastraflow.apparel_core.doc_events.sales_order.before_cancel",
		"on_cancel": "vastraflow.apparel_core.doc_events.sales_order.on_cancel",
	}
}

after_install = "vastraflow.install.after_install"
after_migrate = "vastraflow.install.after_migrate"
