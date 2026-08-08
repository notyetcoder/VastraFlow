app_name = "vastraflaw"
app_title = "VastraFlaw ERP"
app_publisher = "VastraFlaw"
app_description = (
	"VastraFlaw ERP - Order Book and Price List for apparel manufacturing."
)
app_email = "dev@vastraflaw.com"
app_license = "mit"

required_apps = ["erpnext"]

app_include_css = "/assets/vastraflaw/css/apparel_matrix.css"

add_to_apps_screen = [
	{
		"name": "vastraflaw",
		"logo": "/assets/vastraflaw/images/vastraflaw_logo.png",
		"title": "VastraFlaw",
		"route": "/app/vastraflaw-order-book",
	}
]