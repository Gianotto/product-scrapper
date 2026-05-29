# Adding a New Product

Step-by-step guide to adding a new ASUS laptop (or any product) to the monitor.

---

## Step 1 — Find the SKU

The SKU is the retailer's part number for the specific configuration you want to
track. Using the exact SKU is critical to avoid monitoring the wrong variant
(e.g. a 60 Hz panel instead of 120 Hz, or a different RAM/storage tier).

**How to find it:**

- **ASUS product page** — visit `https://www.asus.com/us/laptops/` and navigate
  to the specific model. The part number appears in the product details section
  (e.g. `UX3405CA-PS99T`).
- **Best Buy** — listed as "Model" on the product page.
- **Amazon** — listed as "ASIN" (Amazon-specific) or under "Item model number"
  in the product details table. The ASUS part number is more reliable.
- **Newegg** — listed as "Model" in the specifications table.

Use the manufacturer part number (e.g. `UX3405CA-PS99T`), not the retailer's
internal ID. This SKU will be used as the search query across all stores.

---

## Step 2 — Add the product to `config.yaml`

Open `config.yaml` and add a new entry to the `products:` list:

```yaml
products:
  # ... existing products ...

  - sku: "UX5405SA-PP088W"
    name: "ASUS Zenbook 14 OLED UX5405 (Ultra 9 285H, 32GB, 1TB, 3K 120Hz)"
    target_price: 1299.00
    must_have_terms:
      - "120Hz"
      - "32GB"
      - "285H"
    blocklist_terms:
      - "FHD+"
      - "60Hz"
      - "Refurbished"
      - "Renewed"
    stores:
      bestbuy: "https://www.bestbuy.com/site/searchpage.jsp?st=UX5405SA-PP088W"
      amazon: "https://www.amazon.com/s?k=UX5405SA-PP088W"
      newegg: "https://www.newegg.com/p/pl?d=UX5405SA-PP088W"
      asus_shop: "https://shop.asus.com/us/search?q=UX5405SA-PP088W"
      ebay: "https://www.ebay.com/sch/i.html?_nkw=UX5405SA-PP088W&_sop=15"
```

**Key fields explained:**

| Field | Guidance |
|---|---|
| `sku` | Manufacturer part number — used as the unique key in logs |
| `name` | Human-readable — appears in Telegram alert messages |
| `target_price` | Alert fires when any store's price is at or below this value |
| `must_have_terms` | All terms must appear in the listing title (case-insensitive). Use to filter for the right panel refresh rate, RAM, and CPU tier |
| `blocklist_terms` | If any of these appear in the title, the result is ignored. Use to exclude older panels, refurbished units, etc. |
| `stores` | Only include stores where this SKU is actually sold. You can omit any store |

**Choosing `must_have_terms` carefully:**

ASUS laptops often have many variants on the same page. Use `must_have_terms`
to pin down the exact spec you want:

- Panel: `"120Hz"` vs `"60Hz"`
- RAM: `"32GB"` vs `"16GB"`
- CPU: `"285H"` vs `"255H"` vs `"125H"`
- Display type: `"OLED"` vs `"IPS"`

---

## Step 3 — Test with dry-run

Before enabling the product for real monitoring, verify the scrapers are finding
the right item:

```bash
.venv/bin/python monitor.py --product UX5405SA-PP088W --dry-run --verbose
```

Look at the output for each store:

```
INFO  Checking bestbuy for SKU=UX5405SA-PP088W
INFO  Best result: $1,349.00 — ASUS Zenbook 14 OLED Ultra 9 285H 32GB 1TB 3K 120Hz
```

If the scraper returns no results, it may be because:
- The SKU is not listed on that store.
- `must_have_terms` is too strict (check the actual listing title).
- The page structure changed and the scraper needs updating.

---

## Step 4 — Verify you have the right variant

Common mistakes:

- **60 Hz vs 120 Hz** — check that `"120Hz"` is in `must_have_terms` and
  `"60Hz"` is in `blocklist_terms`.
- **Wrong RAM tier** — if the store sells both 16 GB and 32 GB configs, add
  `"32GB"` to `must_have_terms` and `"16GB"` to `blocklist_terms`.
- **Refurbished listings** — add `"Refurbished"` and `"Renewed"` to
  `blocklist_terms` for Amazon and eBay.
- **Wrong model** — if the SKU returns results from a related but different
  model, tighten `must_have_terms` with a distinguishing term.

After confirming everything looks correct, the product will be checked on the
next scheduled cron run (or run `python monitor.py --product NEW-SKU` manually
to check immediately).
