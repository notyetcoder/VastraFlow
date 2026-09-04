# VastraFlow

Garment order entry, matrix pricing and automatic BOM generation for ERPNext.

VastraFlow extends the standard ERPNext Sales Order with an apparel specification
(product type, fabric, collar, sublimation, stitching, buttons, sleeve), a size/sleeve
quantity matrix, matrix-based pricing, and a BOM engine that builds real ERPNext BOMs
on demand so nobody has to key them in by hand.

## Install

```bash
bench get-app vastraflow /path/to/vastraflow
bench --site your-site install-app vastraflow
```

That is the whole install. `after_install` creates the custom fields and fills
VastraFlow Settings with working defaults.

Then open **VastraFlow Settings** and press **Load Starter Data** to create sample
garments, fabrics, collars, trims, price rows and BOM recipes so you can try the
flow immediately. The General tab shows a readiness checklist.

Requires ERPNext (tested on v16). If you install onto a site whose ERPNext setup
wizard has not run yet, the defaults are applied the first time you open Settings.

## The one rule that matters

Every VastraFlow behaviour is gated behind the **Is Garment Order** checkbox on the
Sales Order. A Sales Order without it ticked behaves exactly like stock ERPNext — no
extra mandatory fields, no extra validation, no size matrix. Ordinary selling is
untouched.

## Settings

Everything is configured from **VastraFlow Settings**; nothing important is hardcoded.

| Tab | What it controls |
|---|---|
| General | Master on/off switch, logo, company, readiness checklist |
| Order Rules | Auto-populate matrix, auto-build the order line, price enforcement, artwork enforcement |
| Sizes | Numeric range (22–54 step 2 by default) or a custom list such as S/M/L/XL, with per-size fabric factors |
| Dropdown Options | The sublimation / sleeve / stitching / button lists. Editing them rewrites the form dropdowns on save |
| Item Rules | Which Item Groups and code prefixes feed the Product, Fabric and Collar pickers |
| Manufacturing | The automatic BOM engine (see below) |
| Activity | Recent garment orders, generated BOMs and errors |

## Automatic BOM

In apparel a BOM per finished-goods combination is unmanageable: product type ×
fabric × collar × sleeve × stitching × buttons runs to thousands of BOMs.

Instead you write **one recipe per product type** (`VastraFlow BOM Rule`) describing
consumption per garment:

- fabric quantity, optionally scaled by the order's size mix
- collar, taken from the order
- any other components — thread, buttons, labels, packaging — on a *Per Garment* or
  *Per Button* basis, optionally restricted to one sleeve type

When an order needs manufacturing, the engine resolves that recipe against the
order's specification, creates a **real ERPNext BOM**, and stamps it with a
signature. The next order with the same specification reuses the stamped BOM rather
than creating another. Use **Preview BOM** on a submitted order to see exactly what
will be produced before anything is created.

The output is an ordinary, fully-costed ERPNext BOM — Work Orders, stock and costing
all behave normally. You just never type one in.

The **BOM Reuse Key** section decides how much specification detail separates two
BOMs. Fewer parts means fewer BOMs; sublimation and size band are off by default
because they usually do not change what materials are consumed.

If a product type has no recipe, the fallback quantities on the Manufacturing tab
are used — or set *When No BOM Rule Exists* to **Block With Error** to require one.

## Pricing

`VastraFlow Price Matrix` prices a product type + fabric + sublimation combination.
Only **submitted** rows are matched and matching is **case-sensitive**, so a row
saved as `Front Sublimation` will not match an order set to `front sublimation`.

The matched rate is shown live on the form while you fill it in. By default an order
cannot be submitted without a match; turn off *Block Submit Without Price* to allow
manual rates.

## What ships

- **DocTypes** — Settings (single), Price Matrix (submittable), BOM Rule, plus the
  Size Matrix, Option, Size and BOM Component child tables
- **Custom fields** — the garment specification on Sales Order, a generated-line
  marker on Sales Order Item, signature fields on BOM
- **Report** — Size-wise Order Summary, pivoting quantities into one column per size
- **Print format** — Production Job Card
- **Workspace** — VastraFlow

## Notes for anyone extending it

- Frappe runs the controller method *before* the app hook, so anything that must
  influence ERPNext's own totals (building the order line) happens in
  `before_validate`, not `validate`.
- Quantities are rounded up against whole-number UOMs. You cannot consume half a
  button, and ERPNext rejects fractions on UOMs flagged *Must Be Whole Number*.
- Dropdown options live in Settings and are pushed onto Custom Fields (Sales Order)
  and a Property Setter (Price Matrix) whenever Settings is saved.
