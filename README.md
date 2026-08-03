# P3 Order Book (p3erp)

A lightweight, apparel-specific order-entry layer built directly on top of
ERPNext's own Sales Order — not a replacement for it, a convenience front
end for it. P3 Order Book adds the fields a garment order actually needs
(fabric, collar, sublimation zones, size/sleeve matrix) that core Sales
Order doesn't have, while every core Sales Order field and behavior stays
untouched.

## Install (bench)

```bash
bench get-app p3erp <repo-url>
bench --site <site-name> install-app p3erp
bench --site <site-name> migrate
```

## How it works

P3 Order Book (`P3O-.YYYY.-.#####`) has three meaningful actions, each
mapped to a real state change:

1. **Save** — Draft (`docstatus 0`). Nothing else is touched.
2. **Submit** — `docstatus 0 → 1`. At this point P3O creates a real
   ERPNext **Sales Order as a Draft** (customer, order date, delivery
   date, one item line for Product Type × Total Qty), links it back via
   the `sales_order` field, then routes to the BOM Decision Engine
   (`bom_engine/manager.py`) to create a Work Order against that real
   Sales Order.
3. **Create Sales Order** (button, visible after Submit) — actually
   submits the linked Sales Order (`docstatus 0 → 1`). This is the
   "officially confirmed, now shows up in every Sales Order report"
   moment.

**Cancelling** a P3 Order Book cascades to the linked Sales Order: cancels
it if it was submitted, deletes it if it was still a draft with nothing
built on top.

## BOM routing strategies

- `BYPASS_BOM` — direct Work Order, no BOM, no material transfer.
- `MATCH_EXISTING` — links an existing active + submitted BOM for the item.
- `AUTO_CREATE` — clones item lines from the most recent existing BOM for
  that item as a template, then submits a new one. Requires at least one
  prior BOM per product to exist as a seed.

## Sublimation zone rules

`sublimation_type` drives which of Front / Back / Sleeves get locked to
"Sublimation"; everything else is restricted to Solid Color / Logo / A4.
Enforced both client-side (`p3_order_book.js`, for UX) and server-side
(`p3_order_book.py validate_sublimation_zones()`, for integrity):

| Sublimation Type | Front | Back | Sleeves |
|---|---|---|---|
| None | free | free | free |
| Front Sublimation | locked | free | free |
| Back Sublimation | free | locked | free |
| Front & Back Sublimation | locked | locked | free |
| Full Sublimation | locked | locked | locked |

"free" = Solid Color / Logo / A4. Solid Color on any zone makes that
zone's colour field mandatory.

## Setup notes before go-live

- **Collar Type** is a Link to `Item`, filtered by `variant_of = 'COLL'`
  (the parent template Item's actual **Item Code**, not its display name
  "Collar" — this distinction is exactly what caused an earlier empty
  dropdown). Set each variant's `image` field so the collar preview on
  the form has something to show.
- **Fabric** works the same way, filtered by `variant_of = 'FB'`.
- **Product Type** is filtered to Item Group `"Products"`.
- **Stitching Type / Colour (x3) / Sublimation Type** are populated live
  from their matching ERPNext `Item Attribute` records (`Stitching`,
  `Colour`, `Sublimation`) at form load — no hardcoded lists, no need to
  redeploy code to add a new value. Add/edit values directly in ERPNext.
- **Pricing — `P3 Item Price List`**: one active rate per Product Type.
  Deliberately its own DocType, never shown on the P3 Order Book form
  itself, so order-taking staff never see or pick a price — it's a
  centrally managed list. **Submit is blocked** on any P3 Order Book
  whose Product Type has no active price entry. The rate is pulled from
  here and applied to the auto-created Sales Order's item line.
- `AUTO_CREATE` needs at least one seed BOM per product line the first
  time it's used for that item.

### Why "same item, different price" isn't actually a conflict

Each P3 Order Book creates its own dedicated Sales Order (never merges
into an existing one), so two different specs for the same base Item
(e.g. two "Hoodies" orders at different rates) just become two separate
Sales Orders — no collision. Each Sales Order item row also gets an
auto-generated `description` summarizing the spec (fabric/collar/
sublimation), which keeps things distinguishable even if you later
choose to consolidate multiple P3 Orders into one combined Sales Order —
ERPNext doesn't block duplicate `item_code` rows within one Sales Order
natively, so that path is open if you want it.

## Roles

- **System Manager** — full access, submit/cancel/amend.
- **Manufacturing Manager** — create/submit/amend.
- **Sales User** — create/write/submit (this doc effectively *is* the
  sales order creation flow for these users, so submit access matches
  what they'd normally have on Sales Order).
