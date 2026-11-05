# Products: starter catalog

`seed_catalog.json` lists about 150 common Philippine hardware and construction items.
A new store picks the ones it sells, and they are copied into its own products (`POST /products/import`).
After import, each store's copy is independent: editing it does not change the catalog or other stores.

There are **no prices** in the catalog. Prices differ per store and change often, so each store sets its own.

## File shape

```json
{
  "version": 1,
  "items": [
    {
      "key": "portland-cement-40kg",
      "name": "Portland Cement 40kg",
      "category": "Cement",
      "base_unit": "bag",
      "aliases": ["semento", "sem", "simento", "cement", "portland", "cement 40kg"],
      "conversions": [{ "from_unit": "kg", "factor": "0.025" }]
    }
  ]
}
```

## Fields

| Field | Meaning |
|---|---|
| `version` | Format version of the file. Bump it if the shape changes. |
| `key` | Stable id for the item (lowercase letters, numbers, dashes). The web app sends these keys to import. **Never change or reuse a key**; add a new item instead. |
| `name` | Display name, specific enough to tell sizes apart: `Deformed Bar 10mm x 6m`, `Common Wire Nail 4"`. Must be unique (ignoring case). |
| `category` | One of: `Cement`, `Steel`, `Wood`, `Nails & Screws`, `Paint`, `Electrical`, `Plumbing`, `Roofing`, `Tools`, `Others`. `Cement` also covers masonry items: hollow blocks, sand, gravel, lime. |
| `base_unit` | The unit stock is counted in. Lowercase. Examples: `pc`, `bag`, `kg`, `m`, `l`, `gal`, `sheet`, `roll`, `cu.m`. |
| `aliases` | How staff actually type or say it: Tagalog (`semento`, `pako 4`, `yero 8`), Taglish (`bakal 10mm`), short forms (`chb 4`, `qde`, `fwe`), common brand-as-word usage (`hardiflex 6`, `rugby`, `vulcaseal`). Lowercase. Each alias may appear on **only one** item, because in a store an alias points to exactly one product. |
| `conversions` | Other units the item is sold in. `{"from_unit": "box", "factor": "25"}` means **1 box = 25 base units** (for nails: 25 kg). `factor` is a string so it stays exact. |

## Rules for conversions

- Only include a conversion when the factor is **exact and common**: cement `kg` → 0.025 bag (40 kg bag), THHN wire `box` → 150 m, paint `l` → 0.25 gal (4 L gallon), long span `ft` → 0.3048 m.
- Skip factors that would round (for example a 6 m rebar: 1 m = 0.1666… pc). Rounded factors make stock drift a little with every sale.
- Don't add metric conversions like `g` → `kg`. The unit service converts g/kg, ml/l, and mm/cm/m automatically.
- Sizes differ by supplier (nail box weight, paint can size). Stores can edit their own copy after import.

## Checking the file

`tests/test_catalog.py` checks every rule above (unique keys, names and aliases, valid categories, lowercase units, positive factors, about 150 items). Run `uv run pytest tests/test_catalog.py` after editing the file.
