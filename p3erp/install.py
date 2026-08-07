import frappe

# Matches the example in the original spec exactly: Fabric, Sublimation,
# Size, Full Sleeve, and Button affect price out of the box; everything
# else stays a pure production spec until someone deliberately switches
# it on (once a real P3 Price Adjustment row exists for it).
DEFAULT_TOGGLES = {
	"Fabric": 1,
	"Sublimation": 1,
	"Size": 1,
	"Sleeve Type": 1,
	"Button": 1,
	"Collar Type": 0,
	"Stitching Type": 0,
	"Thread Color": 0,
	"Packaging": 0,
	"Label": 0,
	"Neck Tape": 0,
}


def after_install():
	seed_price_attribute_toggles()


def seed_price_attribute_toggles():
	for attribute_name, affects_price in DEFAULT_TOGGLES.items():
		if frappe.db.exists("P3 Price Attribute Toggle", attribute_name):
			continue
		frappe.get_doc(
			{
				"doctype": "P3 Price Attribute Toggle",
				"attribute_name": attribute_name,
				"affects_price": affects_price,
			}
		).insert(ignore_permissions=True)
	frappe.db.commit()
