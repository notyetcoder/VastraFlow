# VastraFlow — Technical Blueprint

**App:** `vastraflow` · **Module:** Apparel Core · **Version:** 1.0.0
**Platform:** Frappe v16 / ERPNext v16 · **Site built on:** `erp.local`
**Status:** installed and verified — 59 automated checks passing

This document specifies everything the app does: schema, rules, formulas, execution
order and operational constraints. It is the reference for anyone extending or
rebuilding it. Field names and defaults below were dumped from the installed schema,
not written from memory.

---

## 1. What the app is

VastraFlow extends the standard ERPNext Sales Order for apparel manufacturing:

- a **garment specification** (product type, fabric, collar, sublimation, stitching, buttons, sleeve)
- a **size × sleeve quantity matrix**
- **matrix-based pricing** keyed on product type + fabric + sublimation
- an **automatic BOM engine** that builds real ERPNext BOMs on demand

### 1.1 The governing design rule

> **Every behaviour is gated behind the `is_garment_order` checkbox.**

A Sales Order without that flag behaves exactly like stock ERPNext — no extra
mandatory fields, no extra validation, no size matrix, no hooks doing work. This is
enforced in one place, `_active(doc)` in `doc_events/sales_order.py`:

```python
def _active(doc) -> bool:
    if not doc.get("is_garment_order"):
        return False
    try:
        return bool(get_settings().enabled)
    except Exception:
        return False
```

Every hook returns immediately if this is false. Two switches turn the app off: the
per-order checkbox, and `VastraFlow Settings.enabled` globally.

### 1.2 Other principles

| Principle | Consequence |
|---|---|
| Nothing business-facing is hardcoded | Sizes, dropdown options and item filters live in Settings |
| Generate real ERPNext documents | BOMs and Work Orders are ordinary records; stock and costing behave normally |
| Reuse over proliferation | BOMs are keyed by a specification signature and shared |
| Install must never half-fail | `after_install` tolerates a site whose ERPNext setup wizard has not run |
| Never silently damage existing data | Generated order lines are marked; an existing default BOM is never displaced |

---

## 2. Installation

```bash
bench get-app vastraflow /path/to/vastraflow
bench --site <site> install-app vastraflow
```

`after_install` → `vastraflow.install.after_install`:

1. `create_all()` — creates all custom fields (idempotent, `update=True`)
2. `seed_settings()` — fills the singleton with working defaults
3. Seeding is wrapped in `try/except`: on a site with no Company or Item Groups it
   rolls back, logs, and lets the install succeed. Defaults are applied later by
   `after_migrate` or by calling `seed_settings()` directly.

`after_migrate` → `create_all()` + `sync_select_options()`, so custom fields and
dropdowns are re-aligned after every `bench migrate`.

**Starter data** — `VastraFlow Settings → Load Starter Data` calls
`api.load_starter_data()` → `demo_data.create_starter_data()`. Idempotent; creates
2 products, 3 fabrics, 2 collars, 3 trims, 6 price rows, 2 BOM rules.

---

## 3. Directory structure

```
vastraflow/
├── hooks.py                     app config, doc_events, doctype_js
├── install.py                   after_install / after_migrate / seed_settings
├── modules.txt                  "Apparel Core"
├── apparel_core/
│   ├── settings.py              settings access, size resolution, option sync
│   ├── custom_fields.py         all custom field definitions
│   ├── pricing.py               price matrix lookup
│   ├── bom_engine.py            automatic BOM + work order generation
│   ├── api.py                   whitelisted endpoints
│   ├── demo_data.py             starter data
│   ├── logging_utils.py         logger + activity feed
│   ├── doc_events/sales_order.py    the Sales Order lifecycle
│   ├── doctype/
│   │   ├── vastraflow_settings/         Single
│   │   ├── vastraflow_price_matrix/     Submittable
│   │   ├── vastraflow_bom_rule/         Standard
│   │   ├── vastraflow_bom_component/    Child
│   │   ├── sales_order_size_matrix/     Child
│   │   ├── vastraflow_option/           Child (reused 4×)
│   │   └── vastraflow_size/             Child
│   ├── report/size_wise_order_summary/
│   ├── print_format/production_job_card/
│   └── workspace/vastraflow/
└── public/
    ├── js/sales_order.js
    └── css/vastraflow.css
```

> Every DocType — **including child tables** — needs a `.py` controller file, or the
> app fails to install with `ImportError: No module named ...`.

---

## 4. Data model

### 4.1 Sales Order Size Matrix (child)

| Field | Type | Notes |
|---|---|---|
| `size` | Data | Label from Settings. Read-only in the grid. |
| `full_sleeve` | Int | default 0, non-negative |
| `half_sleeve` | Int | default 0, non-negative |
| `sleeveless` | Int | default 0, non-negative |
| `row_total` | Int | computed, read-only |

### 4.2 VastraFlow Price Matrix (submittable)

Naming series `VFPM-.YYYY.-.MM.-`

| Field | Type | Notes |
|---|---|---|
| `product_type` | Link → Item | required |
| `fabric` | Link → Item | required |
| `sublimation_type` | Select | required; options driven by Settings via Property Setter |
| `rate` | Currency | required, must be > 0 |
| `currency` | Link → Currency | required, default `INR` |
| `amended_from` | Link | standard submittable field |

**Rules** (`vastraflow_price_matrix.py`)
- `rate > 0`, else throw.
- Duplicate guard: only one **submitted** row may exist per
  `product_type + fabric + sublimation_type`. The error links to the existing row.

### 4.3 VastraFlow BOM Rule

Autonamed `field:product_type` — the product type *is* the record name, giving one
recipe per product type.

| Field | Type | Default | Notes |
|---|---|---|---|
| `product_type` | Link → Item | | required, unique |
| `is_active` | Check | 1 | inactive rules are ignored |
| `description` | Small Text | | |
| `use_order_fabric` | Check | 1 | take fabric from the order — one recipe covers all fabrics |
| `fixed_fabric_item` | Link → Item | | required only when `use_order_fabric` is off |
| `fabric_qty_per_unit` | Float | 1.2 | required, > 0 |
| `fabric_uom` | Link → UOM | | blank = item stock UOM |
| `size_scaling` | Check | 0 | scale fabric by the order's size mix |
| `base_size` | Data | 38 | shown when `size_scaling` |
| `fabric_per_size_step` | Float | 0.03 | extra fabric per size step |
| `include_collar` | Check | 1 | pull the collar from the order |
| `collar_qty_per_unit` | Float | 1 | |
| `components` | Table → VastraFlow BOM Component | | everything else |

**Rules** (`vastraflow_bom_rule.py`)
- `fabric_qty_per_unit > 0`
- `use_order_fabric` off ⇒ `fixed_fabric_item` required
- `include_collar` on with qty ≤ 0 ⇒ coerced to 1
- Components: qty > 0; no duplicate `(item_code, apply_if_sleeve)`; a garment may not
  consume itself.

### 4.4 VastraFlow BOM Component (child)

| Field | Type | Default | Notes |
|---|---|---|---|
| `item_code` | Link → Item | | required |
| `qty_per_unit` | Float | 1 | required |
| `uom` | Link → UOM | | blank = item stock UOM |
| `basis` | Select | Per Garment | `Per Garment` \| `Per Button` |
| `apply_if_sleeve` | Select | All | `All` \| `Full Sleeve` \| `Half Sleeve` \| `Sleeveless` |

`Per Button` multiplies `qty_per_unit` by the order's button count:
`{none: 0, one: 1, two: 2, three: 3, four: 4}` (case-insensitive; unknown → 0).
A component resolving to qty 0 is dropped.

### 4.5 VastraFlow Option (child, reused 4×)

| Field | Type | Notes |
|---|---|---|
| `option_value` | Data | required — the exact dropdown text |
| `description` | Data | note only |

### 4.6 VastraFlow Size (child)

| Field | Type | Default | Notes |
|---|---|---|---|
| `size_label` | Data | | required, must be unique |
| `fabric_factor` | Float | 1 | multiplier on base fabric consumption |
| `is_active` | Check | 1 | |

---

## 5. Custom fields

### 5.1 Sales Order (22 fields, all inserted after `total_qty`)

| Field | Type | Behaviour |
|---|---|---|
| `vf_garment_section` | Section Break | "GarmentOS — Garment Specification" |
| `is_garment_order` | Check | **the master gate**; in standard filter |
| `product_type` | Link → Item | `mandatory_depends_on: eval:doc.is_garment_order` |
| `fabric` | Link → Item | mandatory when garment |
| `collar_type` | Link → Item | optional |
| `sublimation_type` | Select | mandatory when garment; options from Settings |
| `sleeve_type` | Select | mandatory when garment; drives matrix columns |
| `stitching_type` | Select | optional (leading blank option) |
| `button_quantity` | Select | optional (leading blank option) |
| `artwork_file` | Attach | in collapsible Artwork section |
| `logo_file` | Attach | printed on the job card |
| `size_matrix` | Table | → Sales Order Size Matrix |
| `garment_total_qty` | Int | read-only, computed |
| `vf_matched_rate` | Currency | read-only, live price preview |
| `garmentos_generated` | Check | hidden, system |
| `garmentos_price_status` | Select | hidden — `Pending` \| `Missing Price` \| `Priced` |

Plus layout breaks: `vf_spec_column`, `vf_artwork_section`, `vf_artwork_column`,
`vf_size_matrix_section`, `vf_totals_section`, `vf_totals_column`.

> **Why `mandatory_depends_on` and not `reqd`.** `reqd: 1` would make these fields
> mandatory on *every* Sales Order in the system, including ordinary non-garment
> sales. That single choice is the difference between an app that coexists with
> ERPNext and one that breaks it.

### 5.2 Sales Order Item

| Field | Type | Purpose |
|---|---|---|
| `vf_generated` | Check (hidden, read-only) | marks the line VastraFlow maintains, so it is updated in place rather than duplicated and manual lines are never touched |

### 5.3 BOM

| Field | Type | Purpose |
|---|---|---|
| `vastraflow_signature` | Data (hidden, read-only, indexed) | the reuse key |
| `vastraflow_auto_generated` | Check (read-only) | marks engine-created BOMs |

---

## 6. Settings reference

`VastraFlow Settings` is a Single doctype organised into seven tabs.

### General
| Field | Default | Effect |
|---|---|---|
| `enabled` | 1 | master switch; off ⇒ no hook does anything |
| `company_logo` | | Attach Image, printed on the job card |
| `default_company` | | |

### Order Rules
| Field | Default | Effect |
|---|---|---|
| `auto_populate_size_matrix` | 1 | fill an empty grid with configured sizes |
| `auto_create_item_line` | 1 | build/update the Sales Order Item from the matrix |
| `block_submit_without_price` | 1 | refuse submission with no matrix match |
| `artwork_enforcement` | Warn Only | `Ignore` \| `Warn Only` \| `Block Submit` |
| `plain_option_value` | Plain | the sublimation value that needs no artwork |

### Sizes
| Field | Default | Effect |
|---|---|---|
| `size_mode` | Numeric Range | `Numeric Range` \| `Custom List` |
| `size_start` / `size_end` / `size_step` | 22 / 54 / 2 | 17 sizes by default |
| `sizes` | | child table for Custom List mode |

### Dropdown Options
Four `VastraFlow Option` tables: `sublimation_options`, `sleeve_options`,
`stitching_options`, `button_options`. Editing them rewrites the live dropdowns on
save (§7.3).

### Item Rules
| Field | Default | Effect |
|---|---|---|
| `product_item_group` | Products | Product Type picker filter |
| `product_code_prefix` | | optional prefix filter |
| `fabric_item_group` | Raw Material | Fabric picker filter |
| `fabric_code_prefix` | FB | |
| `collar_item_group` | | optional |
| `collar_code_prefix` | COLL | |

### Manufacturing
| Field | Default | Effect |
|---|---|---|
| `enable_auto_bom` | 1 | master switch for the BOM engine |
| `reuse_matching_bom` | 1 | reuse a BOM with the same signature |
| `auto_submit_bom` | 1 | a BOM must be submitted for a Work Order to use it |
| `bom_missing_rule_action` | Use Defaults Below | or `Block With Error` |
| `bom_company` / `bom_currency` | | blank = order's company / company default |
| `auto_create_work_order` | 0 | create a Work Order on Sales Order submit |
| `work_order_qty_source` | Size Matrix Total | or `Sales Order Item Qty` |
| `default_fabric_qty` | 1.2 | fallback when no BOM Rule exists |
| `default_fabric_uom` | | |
| `include_collar_in_bom` | 1 | fallback collar behaviour |
| `default_collar_qty` | 1 | |
| `signature_includes_sublimation` | 0 | separate BOM per sublimation type |
| `signature_includes_size_band` | 0 | separate BOM per size band |

### Activity
`log_viewer_html` — renders recent garment orders, generated BOMs and errors.

**Settings validation** (`vastraflow_settings.py`)
- Custom List mode: at least one size, labels unique
- Numeric Range: `size_step > 0`, `size_end ≥ size_start`, span ≤ 200
- `plain_option_value` not in the sublimation list ⇒ warning (not a block)
- `on_update` → `sync_select_options()`, wrapped so a sync failure never blocks the save

---

## 7. Business logic

### 7.1 Hook execution order — the critical detail

Frappe composes document hooks so that **the controller method runs first and the app
hook runs second**:

```
controller.before_validate()  →  vastraflow.before_validate()
controller.validate()         →  vastraflow.validate()
```

ERPNext calculates item totals, taxes and grand total inside
`SalesOrder.validate()`. Therefore **anything that must influence those totals has to
happen in `before_validate`**. Building the order line in `validate` would produce an
order whose totals do not match its lines.

Registered hooks (`hooks.py`):

| Hook | Function |
|---|---|
| `before_validate` | matrix, normalisation, totals, spec validation, pricing, line sync |
| `validate` | artwork enforcement, logging |
| `before_submit` | price gate |
| `on_submit` | logging, optional Work Order |
| `on_update_after_submit` / `before_cancel` / `on_cancel` | logging |

> The original blueprint specified `on_form_load`. That is **not a Frappe doc_event**
> and would never have fired.

### 7.2 `before_validate` — step by step

1. **`_ensure_size_matrix`** — if `auto_populate_size_matrix` and the grid is empty,
   append one row per configured size. Never touches a grid that already has rows, so
   entered quantities are safe.
2. **`_normalize_sleeves`** — zero every sleeve column except the one matching
   `sleeve_type`, then set `row_total` for each row.
3. **`garment_total_qty`** = Σ(`full_sleeve` + `half_sleeve` + `sleeveless`).
4. **`_validate_specification`** — throws on missing `product_type` / `fabric` /
   `sublimation_type` / `sleeve_type`, an empty matrix, or a zero total.
5. **Price lookup** → sets `vf_matched_rate` and
   `garmentos_price_status` (`Priced` / `Missing Price`).
6. **`_sync_item_line`** if `auto_create_item_line`.

> Step 4 runs here rather than in `validate` deliberately. With a zero-quantity matrix
> no order line is built, and ERPNext crashes on an itemless order
> (`TypeError: bad operand type for abs(): 'NoneType'`) before a friendlier message
> could be shown. Validating earlier turns a stack trace into "Total quantity in the
> Size Matrix is zero."

### 7.3 Dropdown option syncing

`sync_select_options()` runs on every Settings save:

- **Sales Order** fields — `frappe.db.set_value` on the Custom Field `options`
- **Price Matrix** `sublimation_type` — a real DocType field, so it needs a
  **Property Setter** (`frappe.make_property_setter`, `is_system_generated=True`)
- Optional fields (`stitching_type`, `button_quantity`) get a leading `\n` so they can
  be cleared
- Followed by `frappe.clear_cache(doctype=...)` for both doctypes

### 7.4 Order line synchronisation

`_sync_item_line(doc, total_qty, rate)` resolves the target row in priority order:

1. an existing row flagged `vf_generated`
2. else a row whose `item_code` equals `product_type`
3. else append a new row

It then sets `vf_generated = 1`, `qty = total_qty`, `uom = item.stock_uom`,
`conversion_factor = 1`, `rate` (when matched) and `delivery_date` (only if blank).
If `product_type` changes on an existing order, the generated line is repointed rather
than duplicated. Manual lines are never modified.

### 7.5 Pricing

```python
frappe.db.get_value("VastraFlow Price Matrix", {
    "product_type": doc.product_type,
    "fabric": doc.fabric,
    "sublimation_type": doc.sublimation_type,
    "docstatus": 1,
}, "rate", order_by="modified desc")
```

- Matching is **exact and case-sensitive**. `Front Sublimation` ≠ `front sublimation`.
- Only **submitted** rows match. A draft price row has no effect.
- Returns `None` on no match; exceptions are logged and swallowed, never raised.

> The original blueprint returned `price_doc[0]`. `frappe.db.get_value` with a single
> fieldname returns a scalar, so that indexed the first character of a string. Fixed.

**`before_submit`** — re-runs the lookup. No match and
`block_submit_without_price` ⇒ throw with the full combination listed. No match with
the setting off ⇒ warn and keep the manually entered rate.

### 7.6 Artwork enforcement

Skipped when `artwork_enforcement == "Ignore"`, when `sublimation_type` equals
`plain_option_value`, or when `artwork_file` is set. Otherwise `Block Submit` throws
at `docstatus == 1`; `Warn Only` shows an orange alert.

---

## 8. The BOM engine

### 8.1 Why it exists

A BOM per finished-goods combination is unmanageable in apparel:
product type × fabric × collar × sleeve × stitching × buttons runs to thousands.

VastraFlow inverts it: **one recipe per product type**, resolved against each order's
specification into a real ERPNext BOM, then shared by every future order with the same
specification.

### 8.2 Fabric quantity

```
base = rule.fabric_qty_per_unit  (or settings.default_fabric_qty when no rule)

if not rule.size_scaling:
    fabric = base

elif size_mode == "Custom List":
    fabric = base × Σ(fabric_factor(size) × qty) / Σ qty

else:                                  # numeric sizes
    avg    = Σ(size × qty) / Σ qty
    fabric = max(base + ((avg − base_size) / size_step) × fabric_per_size_step, 0)
```

Non-numeric sizes in Numeric Range mode make `weighted_average_size` return `None`,
and the base quantity is used unscaled.

### 8.3 Signature — the reuse key

```python
parts = [product_type, fabric, collar_type, sleeve_type,
         stitching_type, button_quantity, company]

if settings.signature_includes_sublimation:
    parts.append(sublimation_type)
if settings.signature_includes_size_band:
    parts.append(f"{fabric_qty:.2f}")

signature = "VF-" + sha1("|".join(parts)).hexdigest()[:12]
```

Sublimation and size band are **off by default**: sublimation is usually a print
process that consumes no distinct material, and including the size band multiplies
BOM count for little gain. Turn them on only when the materials genuinely differ.

### 8.4 Generation algorithm

```
get_or_create_bom(doc):
  1. enable_auto_bom off              → throw / return None
  2. no product_type                  → throw / return None
  3. rule = active BOM Rule for product_type
     no rule + "Block With Error"     → throw
  4. fabric_qty = compute_fabric_qty()
     signature  = compute_signature()
  5. reuse_matching_bom and a submitted, active BOM with that
     signature exists                 → return it
  6. items = build_bom_items()
     empty                            → throw / return None
  7. create BOM:
       item=product_type, quantity=1, is_active=1,
       with_operations=0, rm_cost_as_per="Valuation Rate",
       is_default = 0 if the item already has a default BOM else 1
       vastraflow_signature, vastraflow_auto_generated=1
  8. auto_submit_bom                  → submit
```

Step 7's `is_default` rule matters: setting `is_default = 1` unconditionally would
displace a hand-built default BOM the customer already relies on.

### 8.5 Component resolution

```
build_bom_items:
  fabric   ← order fabric, or rule.fixed_fabric_item when use_order_fabric is off
             qty = compute_fabric_qty()
  collar   ← order collar, when rule.include_collar / settings.include_collar_in_bom
  others   ← rule.components, each:
               skip if apply_if_sleeve ∉ {All, order's sleeve_type}
               qty ×= button_count  when basis == "Per Button"
               skip if qty ≤ 0
```

**UOM resolution** — `_resolve_uom(item, wanted)` uses the requested UOM only when it
equals the item's stock UOM or a `UOM Conversion Detail` exists; otherwise it falls
back to stock UOM. Silent fallback beats a hard failure mid-BOM.

**Whole-number rounding** — `_round_for_uom` rounds **up** on any UOM flagged
`must_be_whole_number`. ERPNext rejects fractional quantities on such UOMs, and you
cannot consume half a button. Without this, a recipe of 0.05 per garment against a
`Nos` item raises `UOMMustBeIntegerError` and no BOM can be produced at all.

### 8.6 Work orders

```
create_work_order(doc, qty=None):
  bom_no = get_or_create_bom(doc)
  qty    = garment_total_qty          (or Σ item qty, per work_order_qty_source)
  qty ≤ 0 → throw
  Work Order: production_item, bom_no, qty, company,
              sales_order, planned_start_date = now
              wip_warehouse / fg_warehouse when resolvable
  inserted as a DRAFT
```

Warehouses resolve as: the item's `Item Default.default_warehouse` → a non-group
warehouse named `Work In Progress` / `Finished Goods` → any non-group warehouse for
the company → left blank. The draft still saves when blank; the user completes it.

> ERPNext v16 `Manufacturing Settings` has **no** `default_wip_warehouse` /
> `default_fg_warehouse` fields. Reading them raises
> `Field ... does not exist on Manufacturing Settings`.

`on_submit` may create the Work Order automatically when `auto_create_work_order` is
on. It is wrapped in `try/except`: a Work Order failure must never roll back an
otherwise valid Sales Order submission.

### 8.7 Worked example

Order: `POLO` / `FB-MICRO` / `COLL-RN` / Full Sleeve / Double Stitching / Two buttons
Matrix: size 36 → 10, size 38 → 20, size 40 → 25 (total **55**)
Rule: base 1.2 m, `size_scaling` on, `base_size` 38, `fabric_per_size_step` 0.03

```
avg size = (36×10 + 38×20 + 40×25) / 55 = 2120 / 55 = 38.5454…
fabric   = 1.2 + ((38.5454 − 38) / 2) × 0.03 = 1.2 + 0.00818 = 1.2082
```

Generated BOM:

| Item | Qty | Source |
|---|---|---|
| FB-MICRO | 1.2082 | fabric, size-scaled |
| COLL-RN | 1.0 | collar from order |
| VF-THREAD | 25.0 | component, Per Garment |
| VF-BUTTON | 2.0 | component, Per Button × 2 |
| VF-POLYBAG | 1.0 | component, Per Garment |

A second order with the same specification reuses this BOM. Changing the fabric to
`FB-COMBOLINE` produces a different signature and a second BOM.

---

## 9. API reference

All under `vastraflow.apparel_core.*`, all `@frappe.whitelist()`.

| Endpoint | Returns |
|---|---|
| `api.get_form_config()` | one call powering the Sales Order form: enabled flags, sizes, link filters, option lists |
| `api.get_setup_status()` | readiness checklist + counts for the Settings General tab |
| `api.resync_options()` | re-applies dropdown lists (System Manager only) |
| `api.load_starter_data()` | creates demo masters (System Manager only) |
| `api.get_attribute_values(attribute_name)` | Item Attribute values, in `idx` order |
| `api.check_product_type(product_type)` | `{status, message}` |
| `pricing.preview_price(product_type, fabric, sublimation_type)` | `{rate, found}` — live form preview |
| `bom_engine.preview_bom(sales_order)` | `{signature, rule, existing_bom, items}` — no side effects |
| `bom_engine.ensure_bom_for_sales_order(sales_order)` | `{bom_no}` |
| `bom_engine.create_work_order_for_sales_order(sales_order, qty=None)` | `{work_order}`; requires `docstatus == 1` |
| `logging_utils.get_recent_activity(limit=30)` | `{errors, orders, boms}` |

`preview_bom`, `ensure_bom_*` and `create_work_order_*` all call
`doc.check_permission("read")` before acting.

**Link filters** are returned as `frm.set_query` dicts rather than a custom query
method — `_filters_to_dict` converts `[["Item","name","like","FB%"]]` into
`{"name": ["like", "FB%"]}`. Disabled items are always excluded.

---

## 10. Client behaviour (`public/js/sales_order.js`)

Loaded via `doctype_js` so it only runs on the Sales Order form.

- `vastraflow.get_config()` — caches `get_form_config` per session
- Applies link filters to `product_type`, `fabric`, `collar_type`
- Populates the size grid client-side when `is_garment_order` is ticked
- `apply_sleeve_columns` — hides non-applicable sleeve columns via
  `grid.update_docfield_property`, wrapped in `try/catch` so a framework difference
  can never break the form
- `recalculate_total` — live `row_total` and `garment_total_qty`
- `refresh_price` — live rate, with an orange headline alert on no match
- On submitted garment orders adds a **Manufacturing** button group: *Preview BOM*
  and *Create Work Order*

---

## 11. Report, print format, workspace

**Size-wise Order Summary** — Script Report on Sales Order. Pivots quantities into one
column per size, with columns generated from Settings (so an S/M/L/XL site gets those
columns). Groups by product type + fabric + sublimation + sleeve. Sizes no longer in
Settings still contribute to `total` but get no column, so history is never silently
dropped. Filters: company, product_type, status, from/to date.

**Production Job Card** — Jinja print format on Sales Order. Shows spec grid, size
breakdown (only the relevant sleeve column), embedded artwork, logo from the order or
Settings, and Cutting / Stitching / QC / Dispatch sign-off lines. Rows with
`row_total == 0` are omitted.

**Workspace** — `VastraFlow`, public, with shortcuts (Garment Orders filtered to
`is_garment_order = 1`, Price Matrix, BOM Rules, Settings) and three link cards.

---

## 12. Logging

Logger name `vastraflow`, via `frappe.logger(..., allow_site=True, file_count=5)`.

| Level | Used for |
|---|---|
| `info` | matrix populated, order validated, price confirmed, BOM generated/reused, Work Order created |
| `warning` | sublimation without artwork, order cancelled |
| `error` | price lookup failure, no price at submit, option sync failure, auto Work Order failure |

`get_recent_activity` reads Error Log, Sales Order and BOM tables rather than the log
file, because the log file is not readable from the browser.

---

## 13. Deviations from the original blueprint

Each of these was a defect in the source document, not a preference.

| # | Original | Problem | Resolution |
|---|---|---|---|
| 1 | `product_type` etc. `reqd: 1` + unconditional `frappe.throw` in `validate` | Would make garment fields mandatory on **every** Sales Order and break all ordinary selling | `is_garment_order` gate + `mandatory_depends_on` |
| 2 | `return price_doc[0]` | `get_value` with one fieldname returns a scalar; this indexed a string | return the value |
| 3 | `on_form_load` hook | Not a Frappe doc_event — never fires | `before_validate` + client JS |
| 4 | Order line built in `validate` | Runs after ERPNext computes totals | moved to `before_validate` |
| 5 | Sizes, options, filters hardcoded | Any change needs a code edit | all moved into Settings |
| 6 | Price Matrix described as "Single" but with naming series and docstatus | Contradictory | submittable doctype |
| 7 | `unique_constraint` in DocType JSON | Not a real DocType property | duplicate check in Python |
| 8 | "Allow Sales" required on fabrics | A Link field does not filter on `is_sales_item`; fabrics are purchase items | products `is_sales_item`, fabrics/trims `is_purchase_item` |
| 9 | No BOM strategy | The stated goal — avoid per-combination BOMs — was unaddressed | the BOM engine (§8) |

---

## 14. Environment and operational notes

These are properties of the deployment, and they cost real debugging time.

**nginx is the entry point, not gunicorn.** This bench runs in production mode.
gunicorn on `:8000` does **not** serve `/assets`, so that port renders an unstyled,
broken desk. Use `http://erp.local` on port 80.

**Multi-site routing.** `config/nginx.conf` was originally generated for a single site
and hardcoded `proxy_set_header X-Frappe-Site-Name site1.localhost`, so *every*
hostname was served site1's data. Fixed with
`sudo -u frappe bench setup nginx --yes` (now uses `$host`, with
`dns_multitenant: true` in `common_site_config.json`).
**Re-run `bench setup nginx` after adding any site**, or the new site silently serves
the first one. The bench template also references a `main` `log_format` that Ubuntu
ships commented out — it must be defined in `/etc/nginx/nginx.conf`.

**File ownership.** gunicorn runs as `frappe`. Running `bench` or scripts as `root`
creates root-owned files under `sites/<site>/logs/`, after which gunicorn dies with
`PermissionError` and the site goes down. Always
`chown -R frappe:frappe sites/<site> apps/<app>` after any root-run command.

**Failed installs leave state.** A failed `install-app` still records the app in
`installed_apps` and leaves the `Module Def` and DocTypes behind, so re-running it
fails with `DuplicateEntryError`. Recover with `bench migrate`, not by re-running
install-app.

**Link field defaults.** A DocType JSON `default` on a Link field pointing at a record
that may not exist will block installation: Frappe re-applies field defaults during
`insert` when a value is `None`, so clearing it in code is not enough. Set such
defaults in `seed_settings` after verifying the record exists.

**Desk routes.** Frappe v16 serves the desk at `/desk/...`; `/app/...` 301-redirects.

**Toolchain.** `bench` is not on `PATH` (`/home/frappe/.local/bin/bench`); `uv` and
`unzip` are not installed — use `env/bin/pip` and Python's `zipfile`.

---

## 15. Verification

59 automated checks across two suites, all passing.

| Area | Covered |
|---|---|
| Order creation | totals, price match, status, auto-built line, item/qty/rate/UOM, grand total, `row_total` |
| Size matrix | population, sleeve normalisation, zero-total rejection |
| Pricing | exact match, missing price blocks submit |
| BOM engine | generation, submission, signature stamping, component resolution, Per Button basis, size scaling to 1.2082, reuse of an identical spec, distinct BOM for a different fabric |
| Work orders | creation, qty, BOM linkage |
| Reporting | report columns and rows, job card rendering |
| API | form config, link filters, setup status, BOM preview |
| **Regression** | **a plain non-garment Sales Order saves and submits with no garment fields, no matrix and untouched quantities** |

The regression check is the most important one in the suite: it is what proves the app
extends ERPNext rather than altering it.

---

## 16. Extending the app

- **A new garment attribute** — add a Custom Field in `custom_fields.py` (gate it with
  `depends_on: eval:doc.is_garment_order`), then decide whether it belongs in the BOM
  signature (§8.3) and/or the price key (§7.5).
- **A new component basis** — extend `basis` options on VastraFlow BOM Component and
  handle it in `build_bom_items`.
- **BOM operations / routing** — the engine sets `with_operations = 0`. Add a routing
  field to the BOM Rule and set `bom.routing` / `bom.with_operations` in
  `get_or_create_bom`.
- **Changing sizes on a live site** — existing orders keep their stored size labels;
  only new grids use the new list. The report keeps old sizes in `total`.
- **Never** reintroduce `reqd: 1` on a Sales Order custom field, and never move order
  line construction out of `before_validate`.

---

## 17. Suggestions from Claude

Things I noticed while building this that are not in the original blueprint. Ordered
by value-to-effort. Nothing here is built yet — these are recommendations.

### High value, small effort

**1. Fabric wastage percentage.** Every cutting operation wastes fabric — typically
5–12% depending on marker efficiency and whether the fabric is striped or checked. The
BOM currently books exactly the computed consumption, so material planning will run
short on every order. Add `wastage_percent` to VastraFlow BOM Rule and apply it in
`compute_fabric_qty`:
`fabric = base × (1 + wastage_percent/100)`. Roughly 15 lines. This is the single
biggest accuracy gap in the app today.

**2. Price validity dates.** `VastraFlow Price Matrix` has one submitted rate per
combination and no time dimension, so raising a price means cancelling and amending,
and history is lost. Add `valid_from` / `valid_upto` and select the row whose window
contains the order's `transaction_date`. Yarn prices move; this will be needed.

**3. Quantity slabs.** Apparel is priced in breaks — 100 pieces and 5,000 pieces are
not the same rate. Add `min_qty` to the Price Matrix and pick the highest `min_qty`
row at or below `garment_total_qty`. Pairs naturally with (2).

**4. Move the test suite into the app.** The 59 checks that verify this build live in
a scratchpad directory and will be lost. Porting them to
`vastraflow/tests/test_*.py` makes `bench --site <site> run-tests --app vastraflow`
work and protects the regression check that proves plain Sales Orders still function.
Mostly mechanical.

### Worth a decision before you scale

**5. Per-size stock: Item Variants.** Right now one Sales Order line carries the total
quantity, so stock and dispatch are tracked at *product* level — the system knows you
sold 55 polos, not that 20 were size 38. If you need per-size inventory, packing lists
or partial dispatch, the ERPNext-native answer is Item Variants on a Size attribute,
with the size matrix generating one line per size. That is a significant change and it
partially reverses the "one line" design, so decide it deliberately rather than
drifting into it. If you only ever manufacture to order and never stock finished
garments, the current design is correct and simpler.

**6. Customer-specific pricing.** The price key is product + fabric + sublimation, with
no customer dimension, so every buyer gets the same rate. If you negotiate per-buyer
rates, add an optional `customer` to the matrix and prefer a customer-specific row over
the generic one.

**7. Operations and routing.** The engine sets `with_operations = 0`, so BOMs carry
materials but no cutting/stitching/finishing steps, and Job Cards cannot track shop
floor progress. Add an optional `routing` to the BOM Rule and pass it through in
`get_or_create_bom` when you want real production tracking.

### Operational

**8. Take a backup before go-live.** `bench --site erp.local backup --with-files`.
There is currently no backup of this site.

**9. Set a real Administrator password.** Development sites are typically created with
a weak throwaway password. Rotate it before the site is reachable by anyone else, and
never commit credentials to this repository.

**10. Consider whether the garment section should be a tab.** It currently sits below
the items table (anchored after `total_qty`). A dedicated Tab Break reads better for
daily order entry, but must be inserted as the *last* tab or it will capture fields
belonging to the following ERPNext tab — which is why it is a section today.

**11. Turn on the scheduler if you want reminders or auto-emails.** New sites are
created with the scheduler disabled.
