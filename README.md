# VastraFlow ERP — GarmentOS Platform (p3erp)

```
VastraFlow ERP
     |
     └── GarmentOS Platform
           |
           ├── Order Book         (P3 Order Book DocType)
           ├── Production Engine  (BOM Decision Engine + Work Order routing)
           ├── Pricing Engine     (P3 Pricing Rule - configurable, priority-based)
           └── Job Card System    (Production Job Card print format)
```

A lightweight, apparel-specific order-entry layer built directly on top of
ERPNext's own Sales Order — not a replacement for it, a purpose-built front
end for it. P3 Order Book adds the fields a garment order actually needs
(fabric, collar, sublimation zones, size/sleeve matrix) that core Sales
Order doesn't have, while every core Sales Order field and behavior stays
untouched.

> **A note on the technical app name**: the underlying Frappe package stays
> `p3erp` (folder, `hooks.py` `app_name`, Python import paths). Renaming
> this on a bench that already has the app installed and migrated is a
> real, higher-risk operation — worth doing deliberately and separately,
> not bundled into a feature build. The VastraFlow/GarmentOS branding
> above is applied everywhere it's safe to (titles, workspace, print
> format), without touching that technical identifier.

## Install (bench)

```bash
bench get-app p3erp <repo-url>
bench --site <site-name> install-app p3erp
bench --site <site-name> migrate
```

## Getting a dashboard icon (do this manually — see note below)

Frappe's own v16 documentation explicitly flags Workspaces as **"still
experimental in v16"** and recommends skipping programmatic workspace
fixtures on this version. Rather than ship a hardcoded Workspace JSON that
could be fighting a schema that's still actively changing, build it live in
the UI instead — 2 minutes, zero version-mismatch risk, always matches
whatever your site's actual current format is:

1. Desk home → **Edit** (top right) → **New Workspace**
2. Name it **"GarmentOS"**, pick an icon
3. Add four **Shortcut** blocks, one per module: P3 Order Book, P3
   Pricing Rule, Production Job Card, Sales Order (or whatever subset you
   want pinned)
4. Save

## How the order → Sales Order → Work Order flow works

Three actions, each mapped to a real state change:

1. **Save** — Draft (`docstatus 0`). Nothing else touched.
2. **Submit** — `docstatus 0 → 1`. Every non-empty cell in the Size &
   Sleeve Matrix must resolve to a matching Pricing Rule (see Pricing
   below) or submit is blocked, listing every missing combination at
   once. A real ERPNext Sales Order is created **as a Draft** — one line
   item per matrix cell, never merged even if two cells share a rate —
   linked back via `sales_order`.
3. **Create Sales Order** button (visible after Submit) — submits the
   linked Sales Order for real (`docstatus 0 → 1`), **then** routes to
   the BOM Decision Engine to create a Work Order against it.

   Work Order creation deliberately happens *here*, not at step 2. ERPNext's
   own `Work Order.validate_sales_order()` requires the linked Sales Order
   to already be submitted — pointing a Work Order at a still-draft Sales
   Order fails with `Sales Order X is not valid`, a real bug hit and fixed
   during development. This also means Work Orders are only ever created
   against a genuinely confirmed Sales Order, never a placeholder draft.

**Cancelling** a P3 Order Book cascades to the linked Sales Order: cancels
it if it was submitted, deletes it if it was still a draft with nothing
built on top.

## Pricing Engine

One unified DocType, **P3 Pricing Rule**, replacing an earlier two-layer
design. Each rule can independently decide *which* of eight possible
parameters actually matter to it — Product Type, Fabric, Collar Type,
Sleeve Type, Size, Stitching Type, Sublimation Type, Customer — via a
`<field>_mandatory` checkbox per parameter. A rule with only Fabric and
Sublimation Type ticked matches *any* order with that combination,
regardless of sleeve, size, or anything else.

**Matching**: exact-match only on whichever fields are ticked mandatory —
untuned/unticked fields are never checked, not even against whatever
value happens to be sitting in them. Multiple active rules can
legitimately overlap and match the same order line at once — that's
expected, not an error. **Priority** (an integer, admin-set) decides
which one wins; ties go to whichever rule was modified most recently.
This mirrors ERPNext's own built-in Pricing Rule engine on purpose.

Every matrix cell always becomes its own separate Sales Order line, even
when two cells resolve to an identical rate.

**Missing pricing at submit time**: submit is blocked, listing every
unmatched (Sleeve Type, Size) combination at once. Users with the
**Account Manager** role get an additional convenience: Frappe's own
standard "New" quick-entry dialog opens automatically, prefilled from the
order's actual spec (all eight parameters pre-ticked Mandatory as the
safest starting point — uncheck whichever shouldn't matter before
saving). Everyone else just sees the blocking message and needs to ask an
Account Manager to add the rule. Note: this currently surfaces and fixes
one missing combination at a time — if an order has several unpriced
combinations, expect to Submit → add pricing → Submit again, repeating
until all are covered, rather than a single dialog resolving everything
in one pass.

## BOM routing strategies

- `MATCH_EXISTING` — links an existing active + submitted BOM for the item.
- `AUTO_CREATE` — clones item lines from the most recent existing BOM for
  that item as a template, then submits a new one. Requires at least one
  prior BOM per product to exist as a seed.

`BYPASS_BOM` (direct Work Order, no BOM, no material transfer) is
disabled, not deleted — the strategy class still exists at
`bom_engine/strategies/bypass_bom.py` for future use, just not wired into
`BOMDecisionEngine.STRATEGY_MAP`. Reasoning: if an order genuinely needs
no BOM/Work Order at all, that's achievable by simply not creating a Work
Order and going straight to Sales Invoice — it doesn't need a dedicated
strategy. Re-enable by re-importing it in `bom_engine/manager.py` and
adding it back to `STRATEGY_MAP` (and back into `bom_strategy`'s Select
options in `p3_order_book.json`).

Work Order creation happens once, when the "Create Sales Order" button is
clicked (not at P3O Submit — see the flow section above for why), at the
whole-order `total_qty` level — it has no awareness of the per-cell
pricing granularity above.

## Sublimation zone rules

`sublimation_type` drives which of Front / Back / Sleeves get locked to
"Sublimation"; everything else is restricted to Solid Color / Logo / A4.
Enforced both client-side (`p3_order_book.js`, for UX) and server-side
(`p3_order_book.py validate_sublimation_zones()`, for integrity), matched
by keyword rather than exact string to tolerate real-world casing
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
  create P3 Pricing Rule entries covering whatever combinations you
  actually sell (not every theoretical one). Broad rules (few mandatory
  fields) cover more ground with less setup; narrow rules (many
  mandatory fields, higher Priority) override them for specific cases.
- `AUTO_CREATE` needs at least one seed BOM per product line the first
  time it's used for that item.

## Roles

- **System Manager** — full access everywhere.
- **Account Manager** — the *only* role (besides System Manager) that
  can create or edit P3 Pricing Rule. Everyone else, including
  Manufacturing Manager, has read-only access to pricing — price stays
  centrally controlled, never something order-taking staff pick.
- **Manufacturing Manager** — create/write/submit/amend on P3 Order Book.
- **Sales User** — create/write/submit/amend on P3 Order Book (this
  document *is* the sales-order-creation flow for these users); **read
  only** on all pricing DocTypes — price stays centrally controlled, never
  something order-taking staff pick.
