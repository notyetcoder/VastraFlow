app_name = "p3erp"
# NOTE ON NAMING: app_name/folder/module import path stays "p3erp" - this
# is the technical Frappe package identifier and renaming it on a bench
# that already has this app installed and migrated is a real, higher-risk
# operation (uninstall/reinstall, python import path changes everywhere)
# that should be done deliberately, on its own, not bundled into a feature
# build. Everything user-facing below carries the new branding instead.
app_title = "VastraFlow ERP"
app_publisher = "VastraFlow"
app_description = (
	"GarmentOS Platform for VastraFlow ERP - Order Book, Production Engine, "
	"Pricing Engine, and Job Card System for apparel manufacturing."
)
app_email = "dev@vastraflow.com"
app_license = "mit"

# This app builds directly on ERPNext DocTypes (Work Order, BOM, Item,
# Sales Order, Customer, Address, Contact) - it cannot function on a bare
# Frappe site. Declaring this means `bench get-app` / site install tooling
# knows to require erpnext rather than failing later at runtime with an
# unclear "DocType not found".
required_apps = ["erpnext"]

# NOTE: VastraFlow's client script (vastraflow.js) is auto-loaded by
# the Frappe framework because it lives alongside the DocType's own folder
# (apparel_core/doctype/vastraflow/). It does NOT need to also be
# registered here via doctype_js - doing so previously caused the refresh
# handler to fire twice per page load.
app_include_css = "/assets/p3erp/css/apparel_matrix.css"

# Seeds the default "Affects Price" toggles (Fabric/Sublimation/Size/
# Sleeve Type/Button on; everything else off) on fresh install - see
# p3erp/install.py. Uses frappe.db.exists() per-row so this is also safe
# to call again on an existing install without duplicating anything.
after_install = "p3erp.install.after_install"

# NOTE: VastraFlow has no doc_events registered here. Its validate/
# on_submit/on_cancel logic lives directly in its own controller
# (apparel_core/doctype/vastraflow/vastraflow.py). There is deliberately
# no BOM/Work Order integration anywhere in this app anymore - it was
# removed; if a Work Order is ever needed for a specific order, create it
# manually from the Sales Order the normal ERPNext way.
