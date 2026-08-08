app_name = "vastraflaw"
# NOTE ON NAMING: app_name/folder/module import path stays "vastraflaw" - this
# is the technical Frappe package identifier and renaming it on a bench
# that already has this app installed and migrated is a real, higher-risk
# operation (uninstall/reinstall, python import path changes everywhere)
# that should be done deliberately, on its own, not bundled into a feature
# build. Everything user-facing below carries the new branding instead.
app_title = "vastraflaw ERP"
app_publisher = "vastraflaw"
app_description = (
	"vastraflaw ERP - Order Book and Price List for apparel manufacturing. "
	"BOM/Work Order routing is deliberately not wired in (see bom_engine/manager.py)."
)
app_email = "dev@vastraflaw.com"
app_license = "mit"

# This app builds directly on ERPNext DocTypes (Item, Sales Order,
# Customer, Address, Contact) - it cannot function on a bare Frappe site.
# Declaring this means `bench get-app` / site install tooling knows to
# require erpnext rather than failing later at runtime with an unclear
# "DocType not found".
required_apps = ["erpnext"]

# NOTE: vastraflaw Order Book's client script is auto-loaded by the
# Frappe framework because it lives alongside the DocType's own folder
# (apparel_core/doctype/vastraflaw_order_book/). It does NOT need to also
# be registered here via doctype_js - doing so previously caused the
# refresh handler to fire twice per page load.
app_include_css = "/assets/vastraflaw/css/apparel_matrix.css"

# Standalone icon on the Frappe "Apps" launcher screen (the grid you get
# to from the app switcher / home dashboard) - this is what gives
# vastraflaw its own dedicated icon separate from ERPNext's standard
# modules, landing straight on the Order Book list when tapped.
add_to_apps_screen = [
	{
		"name": "vastraflaw",
		"logo": "/assets/vastraflaw/images/vastraflaw_logo.png",
		"title": "vastraflaw",
		"route": "/app/vastraflaw-order-book",
	}
]

# NOTE: vastraflaw Order Book has no doc_events registered here. Its
# validate/on_submit/on_cancel logic lives directly in its own controller
# (apparel_core/doctype/vastraflaw_order_book/vastraflaw_order_book.py).
# There is deliberately no BOM/Work Order integration anywhere in this
# app anymore - it was removed; if a Work Order is ever needed for a
# specific order, create it manually from the Sales Order the normal
# ERPNext way.
