"""Install and migrate hooks.

Goal: `bench install-app vastraflow` leaves a site that works, with sensible
defaults already filled in and every dropdown populated. No manual post-install
checklist.
"""

import frappe

from vastraflow.apparel_core.custom_fields import create_all
from vastraflow.apparel_core.logging_utils import get_logger
from vastraflow.apparel_core.settings import sync_select_options

DEFAULT_SUBLIMATION = [
	("Plain", "No print"),
	("Front Sublimation", ""),
	("Back Sublimation", ""),
	("Front & Back sublimation", ""),
	("Full sublimation", "All-over print"),
]
DEFAULT_SLEEVE = [("Full Sleeve", ""), ("Half Sleeve", ""), ("Sleeveless", "")]
DEFAULT_STITCHING = [("Single Stitching", ""), ("Double Stitching", "")]
DEFAULT_BUTTON = [("None", ""), ("One", ""), ("Two", "")]


def after_install():
	create_all()

	# Seeding depends on records ERPNext only creates once its setup wizard has run
	# (Company, Item Groups). A fresh site may not have them yet, and that must not
	# fail the installation - `bench execute vastraflow.install.seed_settings` or
	# simply opening VastraFlow Settings will finish the job later.
	try:
		seed_settings()
	except Exception as exc:
		get_logger().error(f"Settings could not be seeded during install: {exc}")
		frappe.db.rollback()
		frappe.msgprint(
			frappe._(
				"VastraFlow installed. Default settings will be applied once ERPNext setup is complete."
			),
			indicator="orange",
		)

	frappe.db.commit()
	get_logger().info("VastraFlow installed")


def after_migrate():
	"""Keep custom fields and dropdowns aligned after every migrate."""
	create_all()
	try:
		sync_select_options()
	except Exception as exc:
		get_logger().error(f"Post-migrate option sync failed: {exc}")
	frappe.db.commit()


def seed_settings(force: bool = False):
	"""Fill the singleton with working defaults on first install."""
	settings = frappe.get_single("VastraFlow Settings")

	# Only seed once - never stomp on a configured site during a re-run.
	already_configured = bool(settings.sublimation_options)
	if already_configured and not force:
		sync_select_options(settings)
		return settings

	settings.enabled = 1
	settings.auto_populate_size_matrix = 1
	settings.auto_create_item_line = 1
	settings.block_submit_without_price = 1
	settings.artwork_enforcement = "Warn Only"
	settings.plain_option_value = "Plain"

	settings.size_mode = "Numeric Range"
	settings.size_start = 22
	settings.size_end = 54
	settings.size_step = 2

	# Only set these when the group genuinely exists - a Link to a missing record
	# fails validation and would block the whole install.
	product_group = _pick_item_group(["Products", "All Item Groups"])
	fabric_group = _pick_item_group(["Raw Material", "All Item Groups"])
	if product_group:
		settings.product_item_group = product_group
	if fabric_group:
		settings.fabric_item_group = fabric_group
	settings.fabric_code_prefix = "FB"
	settings.collar_code_prefix = "COLL"

	settings.enable_auto_bom = 1
	settings.reuse_matching_bom = 1
	settings.auto_submit_bom = 1
	settings.auto_create_work_order = 0
	settings.bom_missing_rule_action = "Use Defaults Below"
	settings.work_order_qty_source = "Size Matrix Total"
	settings.default_fabric_qty = 1.2
	settings.include_collar_in_bom = 1
	settings.default_collar_qty = 1
	settings.signature_includes_sublimation = 0
	settings.signature_includes_size_band = 0

	for table, values in (
		("sublimation_options", DEFAULT_SUBLIMATION),
		("sleeve_options", DEFAULT_SLEEVE),
		("stitching_options", DEFAULT_STITCHING),
		("button_options", DEFAULT_BUTTON),
	):
		settings.set(table, [])
		for value, description in values:
			settings.append(table, {"option_value": value, "description": description})

	company = frappe.db.get_value("Company", {}, "name")
	if company:
		settings.default_company = company

	settings.flags.ignore_permissions = True
	settings.save()
	get_logger().info("VastraFlow Settings seeded with defaults")
	return settings


def _pick_item_group(candidates: list[str]) -> str | None:
	for name in candidates:
		if frappe.db.exists("Item Group", name):
			return name
	return None
