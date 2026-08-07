# VastraFlow ERP — GarmentOS Platform (p3erp)

```
VastraFlow ERP
     |
     └── GarmentOS Platform
           |
           ├── VastraFlow          (the order-entry DocType itself)
           ├── Pricing Engine      (Base Prices / Price Adjustments / Price Calculator)
           └── Job Card System     (Production Job Card print format)
```

A lightweight, apparel-specific order-entry layer built directly on top of
ERPNext's own Sales Order — not a replacement for it, a purpose-built front
end for it. VastraFlow adds the fields a garment order actually needs
(fabric, collar, sublimation zones, size/sleeve matrix) that core Sales
Order doesn't have, while every core Sales Order field and behavior stays
untouched.

> **A note on the technical app name**: the underlying Frappe package
> stays `p3erp` (folder, `hooks.py` `app_name`, Python import paths).
> Renaming this on a bench that already has the app installed is a real,
> higher-risk operation — worth doing deliberately and separately. The
> VastraFlow branding is applied everywhere it's safe to (the DocType
> itself, titles, print format), without touching that identifier.

## ⚠️ If you already have real data on your live site — read this first

The main DocType was renamed from `P3 Order Book` to `VastraFlow` in this
version. If you have **zero real records** in `P3 Order Book` on your
live site, you can skip straight to Install below - a normal `bench
migrate` will just clean up the old (empty) doctype automatically, the
same way `Apparel Order Spec` was cleaned up earlier in this project.

If you have **real records already saved**, do NOT just drop this code in
and migrate - Frappe's migrate step deletes any doctype whose name no
longer matches the code, which would silently delete your existing table.
Instead, on your live site, **before** pulling this update:

```bash
bench --site <site-name> console
```
```python
frappe.rename_doc("DocType", "P3 Order Book", "VastraFlow", force=True)
frappe.db.commit()
```

This properly renames the doctype and its table in place, preserving all
existing records. *Then* pull this update and run `bench migrate` as normal.

## Install (bench)

```bash
bench get-app p3erp <repo-url>
bench --site <site-name> install-app p3erp
bench --site <site-name> migrate
```

Installing seeds default "Affects Price" toggles automatically (see
Pricing Engine below) - Fabric, Sublimation, Size, Sleeve Type, and Button
are on by default; everything else starts off.

## Getting a dashboard icon

Frappe's own v16 documentation explicitly flags Workspaces as **"still
experimental in v16"** and recommends skipping programmatic workspace
fixtures on this version - so this isn't shipped as app code, for the same
reason a hardcoded print format schema bit us once already: don't bet
against a schema Frappe itself says is still shifting. Build it live in
the UI instead — 2 minutes, zero version-mismatch risk:

1. Desk home → **Edit** (top right) → **New Workspace**
2. Name it **"VastraFlow"**. Use the uploaded VastraFlow star/burst logo
   as the icon if your Frappe version supports custom icon uploads on
   Workspaces (Settings → Icon → Upload); otherwise pick the closest
   built-in icon.
3. Add **Shortcut** blocks: VastraFlow, P3 Base Price, P3 Price
   Adjustment, P3 Price Attribute Toggle, Price Calculator (the page,
   findable by exact name), Production Job Card.
4. Save.

## How the order → Sales Order flow works

Two actions, each mapped to a real state change - **no BOM/Work Order
step anywhere in this app**, by explicit decision. If a Work Order is
ever needed for a specific order, create it manually from the Sales
Order the normal ERPNext way.

1. **Submit** (after Save) — `docstatus 0 → 1`. Every non-empty cell in
   the Size & Sleeve Matrix must resolve to a Base Price (see Pricing
   Engine below) or submit is blocked, listing every missing combination
   at once. A real ERPNext Sales Order is created **as a Draft** — one
   line item per matrix cell, never merged even if two cells share a
   rate — linked back via `sales_order`.
2. **Create Sales Order** button (visible after Submit) — submits the
   linked Sales Order for real (`docstatus 0 → 1`). That's the end of the
   flow.

**Cancelling** cascades to the linked Sales Order: cancels it if it was
submitted, deletes it if it was still a draft with nothing built on top.

## Pricing Engine

Three parts, and a shared calculation module (`apparel_core/pricing.py`)
that both the real order flow and the interactive calculator call into -
never two separate implementations of "how price is computed," so the
calculator can never show something that doesn't match what an order
actually gets charged.

### 🧵 Base Prices (`P3 Base Price`)

Keyed on **Fabric** (always required) with **Product Type** and
**Customer** both optional - which ones are set determines the priority
tier a row serves:

| Customer | Product Type | Tier |
|---|---|---|
| ✅ set | ✅ set | Customer Rule (product-specific) — highest priority |
| ✅ set | blank | Customer Rule (any product) |
| blank | ✅ set | Product Rule |
| blank | blank | Global Rule — the broadest fallback |

Looked up in exactly that order. If nothing matches at any tier, that's
the "Default" case — no price exists, and an order using that exact
combination is blocked at Submit, not guessed.

### ➕ Price Adjustments (`P3 Price Adjustment`)

Universal, additive, and independent of Product Type entirely — one row
per (Attribute, Specific Value) pair, e.g. `Sublimation = "Front
Sublimation"` → `+15`. A missing adjustment row is **not** an error, it's
treated as `+0` — most attribute values don't actually change cost, so
this avoids needing every theoretical combination priced explicitly.
Also gated by the toggle below: an attribute with "Affects Price" off is
never looked up at all, even if adjustment rows exist for it.

**Final price = Base Rate + sum of all applicable Price Adjustments.**

### ☑ Affects Price toggles (`P3 Price Attribute Toggle`)

One row per attribute category with a single checkbox. This is what
makes the system future-proof: **Collar Type, Stitching Type, Thread
Color, Packaging, Label,** and **Neck Tape** all start OFF — they're
production specs today, not pricing inputs. Flip a toggle on (and add
real `P3 Price Adjustment` rows for it) the moment one of them needs to
start affecting cost, with zero code changes required. Defaults seeded on
install: Fabric, Sublimation, Size, Sleeve Type, and Button are ON; the
rest are OFF.

Note: Thread Color, Packaging, Label, and Neck Tape don't have matching
fields on the VastraFlow form yet — they exist in the toggle registry as
forward-looking placeholders. Add the actual fields when/if they're
needed; the pricing lookup will pick them up automatically once both the
field and its toggle exist.

### 🧮 Price Calculator (page, not a doctype)

An interactive simulator at **Price Calculator** in the Desk search bar —
pick any Fabric/Product/Size/Sleeve/Sublimation/Customer combination and
see the live computed price, including which tier the base rate came
from and which adjustments applied. Calls the exact same
`pricing.calculate_price()` function real order submission uses.

### Account Manager quick-entry

On Submit, if a combination has no matching Base Price and the current
user has the **Account Manager** role, Frappe's own standard "New"
quick-entry dialog opens automatically for `P3 Base Price`, prefilled
with this order's Fabric + Product Type. Everyone else just sees the
blocking message and needs to ask an Account Manager to add it. Only
System Manager and Account Manager can create/edit anything in the
Pricing Engine — everyone else (including Manufacturing Manager) is
read-only.

## Sublimation zone rules

`sublimation_type` drives which of Front / Back / Sleeves get locked to
"Sublimation"; everything else is restricted to Solid Color / Logo / A4.
Enforced both client-side (`vastraflow.js`, for UX) and server-side
(`vastraflow.py validate_sublimation_zones()`, for integrity), matched by
keyword rather than exact string to tolerate real-world casing
inconsistencies in the ERPNext attribute data.

## Setup notes before go-live

- **Collar Type / Fabric** are Links to `Item`, filtered by `variant_of`
  (`COLL` / `FB` — the parent template's actual Item Code, not its
  display name).
- **Product Type** is filtered to Item Group `"Products"`.
- **Stitching Type / Colour (x5) / Sublimation Type** are populated live
  from their matching ERPNext `Item Attribute` records at form load — no
  hardcoded lists.
- **Pricing must be populated before any order can be submitted** —
  at minimum, add a Global (Fabric-only) Base Price for every fabric you
  actually sell. Product- and Customer-specific overrides are optional,
  added only where they're actually needed.

## Roles

- **System Manager** — full access everywhere.
- **Account Manager** — the *only* role (besides System Manager) that
  can create or edit anything in the Pricing Engine. Everyone else,
  including Manufacturing Manager, has read-only access to pricing.
- **Manufacturing Manager** — create/write/submit/amend on VastraFlow.
- **Sales User** — create/write/submit/amend on VastraFlow (this document
  *is* the sales-order-creation flow for these users); read-only on
  pricing.
