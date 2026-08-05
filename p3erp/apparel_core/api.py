"""Whitelisted helpers for P3 Order Book's dropdowns.

Why this file exists:

1. `Item Attribute Value` is a child table of `Item Attribute`. Its
   primary key (`name`) is an internal auto-generated hash, not the
   human-readable value - linking a field directly to it (as earlier
   versions of this app did) means the form stores and displays that
   hash instead of e.g. "Soft Micro" or "Double Stitching". It also runs
   into stricter internal-column permission checks in newer Frappe when
   filtered by `parent` through the generic Link search endpoint (the
   `Item.parent` permission error).

   Fix: never link to Item Attribute Value directly. Load attribute
   values through their *parent* `Item Attribute` document instead
   (`get_attribute_values` below) - that's always permission-safe since
   it's just reading a normal doc's own child table - and hand back
   clean, trimmed text. These get used to populate Select field options
   at runtime instead of a Link field.

2. "Most used first" ordering for Link fields (Product Type, Fabric,
   Collar Type) - a custom query function that ranks by how often each
   value has actually been used on existing P3 Order Book records.
"""

import frappe


@frappe.whitelist()
def get_attribute_values(attribute):
	"""Return cleaned, de-duplicated attribute_value strings for a given
	Item Attribute name (e.g. "Stitching", "Colour", "Sublimation"),
	ordered by how often each value appears on existing P3 Order Book
	records (most used first), falling back to their original order in
	Item Attribute for anything never used yet.
	"""
	if not attribute or not frappe.db.exists("Item Attribute", attribute):
		return []

	doc = frappe.get_doc("Item Attribute", attribute)

	seen = set()
	values = []
	for row in doc.item_attribute_values:
		val = (row.attribute_value or "").strip()
		if val and val not in seen:
			seen.add(val)
			values.append(val)

	return _rank_by_usage(values, _guess_fieldname(attribute))


def _guess_fieldname(attribute):
	"""Map an Item Attribute name to the P3 Order Book fieldname(s) whose
	usage should inform ranking. Falls back to no ranking data (just
	keeps Item Attribute's own order) if we don't recognise it.
	"""
	return {
		"Stitching": ["stitching"],
		"Colour": ["front_colour", "back_colour", "sleeve_colour"],
		"Sublimation": ["sublimation_type"],
	}.get(attribute, [])


def _rank_by_usage(values, fieldnames):
	if not values or not fieldnames:
		return values

	counts = {v: 0 for v in values}
	for fieldname in fieldnames:
		rows = frappe.db.sql(
			f"""
			SELECT `{fieldname}` AS val, COUNT(name) AS cnt
			FROM `tabP3 Order Book`
			WHERE `{fieldname}` IN %(values)s
			GROUP BY `{fieldname}`
			""",
			{"values": values},
			as_dict=True,
		)
		for r in rows:
			counts[r.val] = counts.get(r.val, 0) + (r.cnt or 0)

	return sorted(values, key=lambda v: (-counts.get(v, 0), values.index(v)))


@frappe.whitelist()
def item_link_query(doctype, txt, searchfield, start, page_len, filters):
	"""Generic 'most used first' query for Link fields pointing at Item,
	scoped by whatever base filter is passed in (item_group or
	variant_of). Used for Product Type, Fabric, and Collar Type.
	"""
	import json as _json

	if isinstance(filters, str):
		filters = _json.loads(filters)
	filters = filters or {}

	usage_fieldname = filters.pop("_usage_fieldname", None)

	conditions = ["i.name LIKE %(txt)s"]
	values = {"txt": f"%{txt}%", "start": start, "page_len": page_len}

	if filters.get("item_group"):
		conditions.append("i.item_group = %(item_group)s")
		values["item_group"] = filters["item_group"]

	if filters.get("variant_of"):
		conditions.append("i.variant_of = %(variant_of)s")
		values["variant_of"] = filters["variant_of"]

	usage_join = ""
	usage_order = "0"
	if usage_fieldname:
		usage_join = f"""
			LEFT JOIN (
				SELECT `{usage_fieldname}` AS item_code, COUNT(*) AS usage_count
				FROM `tabP3 Order Book`
				WHERE docstatus < 2 AND `{usage_fieldname}` IS NOT NULL
				GROUP BY `{usage_fieldname}`
			) u ON u.item_code = i.name
		"""
		usage_order = "COALESCE(u.usage_count, 0)"

	query = f"""
		SELECT i.name, i.item_name
		FROM `tabItem` i
		{usage_join}
		WHERE {' AND '.join(conditions)}
		ORDER BY {usage_order} DESC, i.item_name ASC
		LIMIT %(start)s, %(page_len)s
	"""
	return frappe.db.sql(query, values)
