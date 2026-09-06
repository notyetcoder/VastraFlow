"""Print-format-only rendering helpers, exposed to Jinja via hooks.py.

Kept separate from api.py (whitelisted endpoints) since nothing here is called
from the browser - only from print format templates, server-side.
"""

import base64
import os
import re

import frappe

# Close enough to the named option for a printed sketch outline - not meant to be a
# precise brand palette.
COLOUR_HEX = {
	"Red": "#dc2626",
	"Green": "#16a34a",
	"Blue": "#2563eb",
	"Black": "#111111",
	"White": "#9ca3af",  # white ink on white paper would be invisible - shown as a light grey outline instead
}

_COLLAR_ASSET_PREFIX = "/assets/vastraflow/images/collars/"
_APP_PUBLIC_DIR = os.path.join(frappe.get_app_path("vastraflow"), "public")


def _read_app_asset(url_path: str) -> bytes | None:
	"""Read one of this app's own /assets/vastraflow/... files straight off disk.

	PDF export on this bench goes through wkhtmltopdf, which fetches every <img src>
	as a real HTTP request - and in production that depends on DNS/host resolution
	working for whatever hostname the site answers to. A real print run showed this
	failing for every collar photo (they rendered as blank/broken placeholders)
	while a smaller logo happened to load - inconsistent and not something to
	depend on. Reading the file directly and inlining it below removes the network
	round-trip entirely for anything that ships inside this app.
	"""
	if not url_path or not url_path.startswith("/assets/vastraflow/"):
		return None
	rel = url_path[len("/assets/vastraflow/") :]
	disk_path = os.path.join(_APP_PUBLIC_DIR, rel)
	try:
		with open(disk_path, "rb") as f:
			return f.read()
	except OSError:
		return None


def _data_uri(url_path: str) -> str | None:
	"""Base64 data: URI for one of this app's own assets, or None to fall back to
	a normal <img src="..."> (used for anything NOT shipped inside this app, e.g. a
	user-uploaded private file - those are numerous/large enough that Frappe's own
	print pipeline already handles them, and re-reading arbitrary user files here
	would be both unnecessary and a bigger surface to get wrong)."""
	data = _read_app_asset(url_path)
	if data is None:
		return None
	ext = os.path.splitext(url_path)[1].lower()
	mime = {".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(
		ext, "application/octet-stream"
	)
	return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def get_collar_visual(item_code: str, colour: str | None = None, size: int = 84) -> str:
	"""Inline, colour-tinted markup for a collar's reference image.

	If the Item's image is one of VastraFlow's own generated sketches, the SVG is
	read from disk and re-coloured to match Collar Colour, then returned as inline
	markup (so the colour actually renders - an <img> tag can't be recoloured by
	CSS reliably). If the user has replaced it with their own photo, that image is
	shown as-is; a photo can't be tinted the same way, and shouldn't be.
	"""
	if not item_code:
		return ""

	image = frappe.db.get_value("Item", item_code, "image")
	if not image:
		return ""

	if image.startswith(_COLLAR_ASSET_PREFIX) and image.endswith(".svg"):
		data = _read_app_asset(image)
		if data is None:
			return f'<img src="{image}" style="width:{size}px;height:{size}px;object-fit:contain">'
		svg = data.decode("utf-8")

		hex_colour = COLOUR_HEX.get((colour or "").strip(), "#111111")
		svg = svg.replace('fill="#111111"', f'fill="{hex_colour}"')
		svg = svg.replace('stroke="#111111"', f'stroke="{hex_colour}"')
		svg = svg.replace('width="120" height="120"', f'width="{size}" height="{size}"')
		return svg

	src = _data_uri(image) or image
	return f'<img src="{src}" style="width:{size}px;height:{size}px;object-fit:contain;border:1px solid #d1d5db;border-radius:4px">'


def brand_mark() -> str:
	"""VastraFlow's own logo, inlined the same way as the collar photos - so it
	never depends on wkhtmltopdf being able to fetch it over the network either."""
	return _data_uri("/assets/vastraflow/images/vastraflow_logo.png") or "/assets/vastraflow/images/vastraflow_logo.png"


def item_display_name(item_code: str | None) -> str:
	"""The Item's real name for print, not its internal code (e.g. "Dotnet", not
	"FB-DN"). Variant items were named "<Template> - <Value>" at catalog-seed time
	(see demo_data.py) - only the value half is useful on a printed spec card."""
	if not item_code:
		return "-"
	name = frappe.db.get_value("Item", item_code, "item_name")
	if not name:
		return item_code
	return name.split(" - ", 1)[-1] if " - " in name else name


_PHONE_LINE = re.compile(r"^\s*phone\s*:\s*(.+)$", re.IGNORECASE)


def customer_block(doc) -> dict:
	"""Address and phone for the print header, cleaned up:

	- at most 2 address lines (a full Address Display can run to 5+ lines and
	  crowd out everything else on the card)
	- exactly one phone line - `address_display` already renders a "Phone: ..."
	  line baked in when the linked Address has one, so showing Contact Mobile
	  *as well* just repeats the same number under two different labels. Contact
	  Mobile wins when set; the phone line pulled out of the address is the
	  fallback, and either way it is shown exactly once.
	"""
	raw = (doc.get("address_display") or "").replace("<br>", "\n").replace("<br/>", "\n")
	lines = [line.strip() for line in raw.split("\n") if line.strip()]

	address_lines = []
	phone_from_address = None
	for line in lines:
		match = _PHONE_LINE.match(line)
		if match:
			phone_from_address = match.group(1).strip()
		else:
			address_lines.append(line)

	return {
		"address_lines": address_lines[:2],
		"phone": doc.get("contact_mobile") or phone_from_address or "-",
	}


# --- Small icon glyphs for print-only spec cards ---------------------------------
def stitching_icon(stitching_type: str | None, width: int = 32, height: int = 14) -> str:
	"""A dashed stitch line - one row for Single Stitching, two for Double."""
	value = (stitching_type or "").strip()
	rows = {"Single Stitching": 1, "Double Stitching": 2}.get(value, 0)
	if not rows:
		return ""
	dash = "".join(f'<rect x="{x}" y="0" width="4" height="2.4" fill="#111111"/>' for x in range(0, width, 7))
	lines = "".join(f'<g transform="translate(0,{r * 6})">{dash}</g>' for r in range(rows))
	total_h = rows * 6 + 3
	# margin-left, not a flex gap, for the same reason noted on collar_strip - this
	# old engine does not reliably honour gap between flex children.
	return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_h}" style="margin-left:5px;vertical-align:middle">{lines}</svg>'


_SLEEVE_ICON_FILES = {
	"Full Sleeve": "full_sleeve",
	"Half Sleeve": "half_sleeve",
	"Sleeveless": "sleeveless",
	"Multi": "multi_sleeve",
}


def sleeve_icon(sleeve_type: str | None, size: int = 40) -> str:
	"""Inline sketch of the sleeve length - Full/Half/Sleeveless/Multi."""
	filename = _SLEEVE_ICON_FILES.get((sleeve_type or "").strip())
	if not filename:
		return ""
	data = _read_app_asset(f"/assets/vastraflow/images/sleeves/{filename}.svg")
	if data is None:
		return ""
	return data.decode("utf-8").replace('width="120" height="120"', f'width="{size}" height="{size}"')


# wkhtmltopdf's bundled QtWebKit (this bench's PDF engine) does not reliably lay
# out CSS Flexbox or Grid at all - confirmed from an actual print run, where every
# flex/grid container fell back to plain vertical block stacking instead of
# columns, tripling the page count. Every side-by-side layout on this card is
# therefore built as a plain HTML <table> instead - the one layout technique that
# has worked unchanged since the 1990s and is what email templates still rely on
# for exactly this reason. It also does not support CSS filter (blur/grayscale) -
# "de-emphasize the non-selected options" is a plain translucent overlay div, not
# filter:blur. Thumbnail sizes are set as real HTML attributes, not just CSS,
# since a class-name mismatch once let full-resolution photos blow out an entire
# page each.
_THUMB_SIZE = 44
_MUTE_OVERLAY = '<div class="vf-mute"></div>'
_DOT = '<div class="vf-dot"></div>'


def _strip_table(cells: list[str]) -> str:
	tds = "".join(f'<td class="vf-opt-cell">{c}</td>' for c in cells)
	return f'<table class="vf-strip"><tr>{tds}</tr></table>'


def collar_strip(selected_item_code: str | None) -> str:
	"""All Collar Type variants as a strip, the selected one full-clarity and the
	rest muted (not hidden) - the same shop-floor idea as circling one option on a
	paper form."""
	items = frappe.get_all(
		"Item", filters={"variant_of": "COLL", "disabled": 0}, fields=["name", "item_name", "image"], order_by="name"
	)
	if not items:
		return ""

	cells = []
	for it in items:
		label = it.item_name.split(" - ", 1)[-1] if " - " in (it.item_name or "") else (it.item_name or it.name)
		selected = it.name == selected_item_code
		if it.image:
			src = _data_uri(it.image) or it.image
			img = f'<img src="{src}" width="{_THUMB_SIZE}" height="{_THUMB_SIZE}">'
		else:
			img = '<span class="vf-noimg">?</span>'
		cells.append(
			f'<div class="vf-opt{" vf-selected" if selected else ""}">'
			f'{_DOT if selected else ""}'
			f'<div class="vf-thumb">{img}{"" if selected else _MUTE_OVERLAY}</div>'
			f'<div class="vf-name">{frappe.utils.escape_html(label)}</div>'
			f"</div>"
		)
	return _strip_table(cells)


_SLEEVE_TYPES_ORDERED = ["Full Sleeve", "Half Sleeve", "Sleeveless", "Multi"]


def sleeve_strip(selected: str | None) -> str:
	"""All four Sleeve Type options as a strip, same mute-not-hide treatment as
	collar_strip - built from the same sketches used elsewhere on the card."""
	cells = []
	for sleeve_type in _SLEEVE_TYPES_ORDERED:
		icon = sleeve_icon(sleeve_type, 32)
		is_selected = sleeve_type == selected
		cells.append(
			f'<div class="vf-opt{" vf-selected" if is_selected else ""}">'
			f'{_DOT if is_selected else ""}'
			f'<div class="vf-thumb">{icon}{"" if is_selected else _MUTE_OVERLAY}</div>'
			f'<div class="vf-name">{sleeve_type}</div>'
			f"</div>"
		)
	return _strip_table(cells)


_BUTTON_COUNTS = {"None": 0, "One": 1, "Two": 2, "Three": 3, "Four": 4}


def button_icon(button_quantity: str | None, size: int = 15) -> str:
	"""A bold filled circle per button, as many as the value says. An earlier
	version drew two stitch holes on each circle to look more like a real button -
	at this print size that read as a small face instead, so it was dropped: a
	plain solid dot is unambiguous, a "clever" one was not."""
	count = _BUTTON_COUNTS.get((button_quantity or "").strip(), 0)
	if count <= 0:
		return ""
	gap = size * 1.4
	width = int(gap * count + size * 0.3)
	circles = "".join(
		f'<circle cx="{int(gap * i + size / 2)}" cy="{int(size / 2)}" r="{size * 0.42}" fill="#111111"/>'
		for i in range(count)
	)
	return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{size}" style="margin-left:4px;vertical-align:middle">{circles}</svg>'
