app_name = "p3erp"
app_title = "P3 Order Book"
app_publisher = "P3ERP"
app_description = "P3 Sales Order Creation Tool for Apparel Manufacturing"
app_email = "dev@p3erp.com"
app_license = "mit"

# This app builds directly on ERPNext DocTypes (Work Order, BOM, Item,
# Sales Order, Customer, Address, Contact) - it cannot function on a bare
# Frappe site. Declaring this means `bench get-app` / site install tooling
# knows to require erpnext rather than failing later at runtime with an
# unclear "DocType not found".
required_apps = ["erpnext"]

# NOTE: P3 Order Book's client script (p3_order_book.js) is auto-loaded by
# the Frappe framework because it lives alongside the DocType's own folder
# (apparel_core/doctype/p3_order_book/). It does NOT need to also be
# registered here via doctype_js - doing so previously caused the refresh
# handler to fire twice per page load.
app_include_css = "/assets/p3erp/css/apparel_matrix.css"

# NOTE: P3 Order Book's on_submit/on_cancel logic (including the call into
# BOMDecisionEngine) lives directly in its own controller
# (p3_order_book.py). Do NOT also wire it up here via doc_events - that
# would fire the BOM engine twice per submit, the same class of bug as the
# duplicate JS registration above.
