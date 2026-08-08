# VastraFlow ERP (p3erp)

```
VastraFlow ERP
     |
     ├── VastraFlow Order Book   (the order-entry DocType itself)
     ├── Price List              (Fabric x Sublimation Type -> Rate)
     └── Job Card System         (Production Job Card print format)
```

A lightweight, apparel-specific order-entry layer built directly on top of
ERPNext's own Sales Order — not a replacement for it, a purpose-built front
end for it. VastraFlow Order Book adds the fields a garment order actually
needs (fabric, collar, sublimation zones, size/sleeve matrix) that core
Sales Order doesn't have, while every core Sales Order field and behavior
stays untouched.

> **A note on the technical app name**: the underlying Frappe package
> stays `p3erp` (folder, `hooks.py` `app_name`, Python import paths).
> Renaming this on a bench that already has the app installed is a real,
> higher-risk operation (no native `bench rename-app`) — worth doing
> deliberately and separately, if ever. The VastraFlow branding is
> applied everywhere it's safe to (DocType names, app title, the Apps
> launcher icon, print format) without touching that identifier.

## ⚠️ If you already have real data on your live site — read this first

The main DocType is renamed from `VastraFlow` to `VastraFlow Order Book`
in this version. **This is now handled automatically** by
`p3erp/patches/v1_0/rename_vastraflow_to_order_book.py`, registered in
`[pre_model_sync]` in `patches.txt` — it runs *before* Frappe syncs the
new doctype json, so it renames the existing table and its data in place
instead of leaving your old records behind under an orphaned table while
a fresh empty one gets created.

That said — this is exactly the kind of operation that deserves a real
backup first, and testing on a staging copy of your site if you have
one, since it hasn't been run against your actual production data:

```bash
bench --site <site-name> backup --with-files
```

Then pull this update and run the normal migrate:

```bash
bench --site <site-name> migrate
```

If anything looks wrong afterward, `frappe.db.exists("DocType",
"VastraFlow Order Book")` and a record count check
(`frappe.db.count("VastraFlow Order Book")`) against your old row count
are the first things worth checking in `bench console`.

### The old pricing doctypes are NOT auto-deleted

`P3 Base Price`, `P3 Price Adjustment`, and `P3 Price Attribute Toggle`
have been removed from this app's code (replaced by the much simpler `P3
Price List` — see below), but their doctype records and tables are
**deliberately left in your database** rather than auto-dropped by a
patch — deleting doctypes/data automatically on a live site is not a
call this codebase should make for you. They'll just sit there, unused
and no longer reachable from any menu, until you decide what to do with
them. Once you've confirmed you don't need the old rates anymore (or
you've copied whatever's useful into the new Price List), you can clean
them up manually from `bench console`:

```python
for dt in ("P3 Base Price", "P3 Price Adjustment", "P3 Price Attribute Toggle"):
    frappe.delete_doc("DocType", dt, force=True, ignore_missing=True)
frappe.db.commit()
```

## Install (bench)

```bash
bench get-app p3erp <repo-url>
bench --site <site-name> install-app p3erp
bench --site <site-name> migrate
```

Fresh installs get an empty `P3 Price List` — there's nothing to seed
automatically since fabric Item codes and rates are specific to your
catalog. Add your rates directly in the list view (fast for a couple
dozen rows), or bulk-import via Frappe's built-in **Data Import** tool
if you have many.

## Dashboard / app-launcher icon

Wired via Frappe's `add_to_apps_screen` hook (`hooks.py`) — this is the
icon grid you get from the app switcher / Frappe's home "Apps" screen,
and it's a stable, documented hook (unlike Workspace fixtures, which
Frappe's own v16 docs still flag as experimental — deliberately not used
here for the same reason a hardcoded schema bit this project once
already). It uses the VastraFlow star/burst logo already bundled at
`p3erp/public/images/vastraflow_logo.png`, and routes straight to the
Order Book list when tapped. No manual setup needed — it shows up
automatically after `bench migrate` + a browser hard-refresh (or `bench
build` if the asset doesn't show up, to make sure the image made it into
the assets bundle).

If you'd also like a proper **Workspace** (the sidebar/dashboard page
inside Desk, distinct from the Apps launcher icon above), that's still
best built live in the UI rather than as a version-fragile fixture — 2
minutes:

1. Desk home → **Edit** (top right) → **New Workspace**
2. Name it **"VastraFlow"**; pick the closest built-in icon (or upload
   the star/burst logo if your Frappe version's Workspace settings
   support custom icon uploads).
3. Add **Shortcut** blocks: **VastraFlow Order Book**, **P3 Price
   List**, **Production Job Card**.
4. Save.

## How the order → Sales Order flow works

Two actions, each mapped to a real state change - **no BOM/Work Order
step anywhere in this app**, by explicit decision. If a Work Order is
ever needed for a specific order, create it manually from the Sales
Order the normal ERPNext way.

1. **Submit** (after Save) — `docstatus 0 → 1`. The order's Fabric +
   Sublimation Type must resolve to a Price List rate (see Pricing
   below) or submit is blocked. A real ERPNext Sales Order is created
   **as a Draft** — one line item per matrix cell, never merged, even
   though every cell on the same order shares the same rate — linked
   back via `sales_order`.
2. **Create Sales Order** button (visible after Submit) — submits the
   linked Sales Order for real (`docstatus 0 → 1`). That's the end of
   the flow.

**Cancelling** cascades to the linked Sales Order: cancels it if it was
submitted, deletes it if it was still a draft with nothing built on top.

## Pricing

Deliberately simple, by design: **Fabric x Sublimation Type -> Rate**,
nothing else. `apparel_core/pricing.py` is the single shared calculation
function the real order-submission flow calls into.

### `P3 Price List`

One row per (Fabric, Sublimation Type) pair, with a Rate. Sublimation
Type is **not** a hardcoded option list on this doctype — it's populated
live from the real `Sublimation` Item Attribute (`p3_price_list.js`),
the exact same source of truth the Order Book's own Sublimation Type
field uses, via the existing `get_attribute_values` API — so adding or
renaming a value in that Item Attribute is all that's needed for it to
be selectable here too, no code change required.

**Everything else — Collar Type, Stitching Type, Size, Sleeve Type,
Button Qty — is a production spec only and never affects price.** If
cost ever needs to vary by one of those in the future, that's a
deliberate, separate redesign of the pricing model — not something this
doctype tries to anticipate.

### Account Manager quick-entry

On Submit, if the order's Fabric + Sublimation Type combination has no
matching Price List row and the current user has the **Account
Manager** role, Frappe's own standard "New" quick-entry dialog opens
automatically for `P3 Price List`, prefilled. Everyone else just sees
the blocking message and needs to ask an Account Manager to add it. Only
System Manager and Account Manager can create/edit the Price List;
Manufacturing Manager has read-only access; **Sales User has no access
to it at all** — order-entry users work the Order Book and never see or
touch prices.

## Sublimation zone rules

`sublimation_type` drives which of Front / Back / Sleeves get locked to
"Sublimation"; everything else is restricted to Solid Color / Logo / A4.
Enforced both client-side (`vastraflow_order_book.js`, for UX) and
server-side (`vastraflow_order_book.py validate_sublimation_zones()`,
for integrity), matched by keyword rather than exact string to tolerate
real-world casing inconsistencies in the ERPNext attribute data.

## Setup notes before go-live

- **Collar Type / Fabric** are Links to `Item`, filtered by `variant_of`
  (`COLL` / `FB` — the parent template's actual Item Code, not its
  display name).
- **Product Type** is filtered to Item Group `"Products"`.
- **Stitching Type / Colour (x5) / Sublimation Type** are populated live
  from their matching ERPNext `Item Attribute` records at form load — no
  hardcoded lists.
- **Pricing must be populated before any order can be submitted** — add
  a `P3 Price List` row for every Fabric x Sublimation Type combination
  you actually sell.

## Roles

- **System Manager** — full access everywhere.
- **Account Manager** — the *only* role (besides System Manager) that
  can create or edit the Price List.
- **Manufacturing Manager** — create/write/submit/amend on VastraFlow
  Order Book; read-only on the Price List.
- **Sales User** — create/write/submit/amend on VastraFlow Order Book
  (this document *is* the sales-order-creation flow for these users);
  **no access at all** to the Price List — cannot view or modify prices.
