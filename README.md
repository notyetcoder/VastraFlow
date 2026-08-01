# P3ERP Apparel Module

Custom Frappe/ERPNext app for dynamic apparel manufacturing: garment
customization specs, a size/sleeve quantity matrix, and a rules-based BOM
routing engine that decides how a submitted spec becomes a Work Order.

## Install (bench)

```bash
bench get-app p3erp <repo-url>
bench --site <site-name> install-app p3erp
bench --site <site-name> migrate
```

## What's in here

- **Apparel Order Spec** (`apparel_core`) — the submittable DocType capturing
  garment attributes, artwork, and the size/sleeve quantity matrix
  (`Sales Order Size Matrix` child table).
- **BOM Decision Engine** (`bom_engine`) — a Strategy-pattern dispatcher
  (`BOMDecisionEngine`) that, on submit, routes the order to one of:
  - `MATCH_EXISTING` — link an existing active/submitted BOM
  - `AUTO_CREATE` — clone a BOM template and submit a new one
  - `BYPASS_BOM` — create a Work Order directly, no BOM/transfer
- **Production Job Card** print format — shop-floor A4 print with sizing
  matrix, artwork preview, and department sign-off table.

## Required setup before using `AUTO_CREATE`

`AUTO_CREATE` clones its raw-material item list from the most recently
modified existing BOM for the same Item. Create at least one BOM (even as a
draft) for any item that will use this strategy — see
`bom_engine/strategies/auto_generate.py` for details.

## Roles

- **System Manager** — full access, submit/cancel/amend.
- **Manufacturing Manager** — create/submit/amend.
- **Sales User** — create/write only (no submit) — intended for capturing
  spec details; a manufacturing role should perform the actual submission
  that triggers Work Order creation.

Adjust `apparel_core/doctype/apparel_order_spec/apparel_order_spec.json`
`permissions` to match your organization's actual roles before go-live.
