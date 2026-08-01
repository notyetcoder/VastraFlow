app_name = "p3erp"
app_title = "P3ERP Apparel System"
app_publisher = "P3ERP"
app_description = "Dynamic Apparel Manufacturing ERP System"
app_email = "dev@p3erp.com"
app_license = "mit"

# NOTE: Apparel Order Spec's client script (apparel_order_spec.js) is
# auto-loaded by the Frappe framework because it lives alongside the
# DocType's own folder (apparel_core/doctype/apparel_order_spec/). It does
# NOT need to also be registered here via doctype_js - doing so previously
# caused the refresh handler (and therefore render_matrix_grid /
# setup_artwork_preview) to fire twice per page load.
app_include_css = "/assets/p3erp/css/apparel_matrix.css"

doc_events = {
	"Apparel Order Spec": {
		"on_submit": "p3erp.bom_engine.manager.BOMDecisionEngine.process_apparel_order"
	}
}
