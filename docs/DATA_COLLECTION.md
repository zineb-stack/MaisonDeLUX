# MaisonDeLUX — Data Collection V2

## Current architecture and source

The historical collector targets the public Mubawab Morocco result category:

```text
https://www.mubawab.ma/fr/sc/appartements-a-vendre
```

Pagination used `:p:{page}`. The original script downloaded only result pages with `requests`, selected `div.listingBox`, and saved four strings: `Titre`, `Prix`, `Localisation`, `Details`. It did **not** download detail pages. It accumulated everything in memory, overwrote `maisonlux_maroc_complet.csv` only at the end, discarded URLs/IDs, and silently ignored card exceptions.

The historical CSV contains 16,858 rows and remains unchanged.

## Information audit

Reliably visible in the historical export: title, displayed price, compact location and compact details (often surface/rooms/bedrooms/bathrooms).

Occasionally visible in text: property type, floor/RDC, construction state, condition, parking, terrace, pool, garden, views, furnishing and other amenities.

Discarded by the old card parser where present: anchor URL and possible card/native ID attributes. Their real coverage and selector stability have **not** been measured live in Phase 5A.

Unavailable from the four-column export: stable source identity, dates, exact address/coordinates, separate land/built surface, systematic condition and complete amenity lists. Some may exist on detail pages, but that must be verified rather than assumed.

## V2 flow

```text
FETCH → PARSE RAW CARD → NORMALIZE → VALIDATE → CHECKPOINT CSV
```

- `fetch_html`: timeout, three conservative attempts for transient errors, and visible logging.
- `parse_listing_card`: raw title/price/location/details plus URL/native ID if actually present.
- `build_v2_record`: transaction, price, location, surfaces, rooms, condition and amenities.
- `validate_listing`: `VALID`, `WARNING` or `INVALID`; no automatic deletion.
- `append_records`: fixed schema, UTF-8, stable-ID deduplication and page-level checkpoints.

The collector defaults to one page and at most 20 new records. Phase 5A did not execute it against the live source.

## Safe source behavior

- Public pages only; no authentication, CAPTCHA, access-control or anti-bot bypass.
- Descriptive project user agent, 20-second timeout and 2–4 second delays between pages.
- HTTP 401, 403 or 429 stops retries immediately and is logged.
- No parallel crawling.
- Before Phase 5B, review the current source terms/robots guidance and stop if automation is prohibited.

## Identity and duplicates

Priority is native website ID, then SHA-256 of canonical source URL, then a deterministic fallback fingerprint of source + normalized title + location + surface + property type. Row numbers are never IDs. Existing IDs are loaded from the output CSV; repeated IDs are skipped before append.

The fallback is weaker than a native ID/URL and receives an explicit `listing_id_strategy` value. Phase 5B must measure how often each strategy is used.

## Sale versus rent

Signals are combined from source category, URL, title and details:

- explicit sale only → `SALE`;
- explicit rent/month only → `RENT`;
- conflict or no reliable signal → `UNKNOWN`.

Unknown is never converted to sale. Only `SALE` records with a valid total price may enter future sale-model training.

## Parsing and validation policy

Price parsing supports MAD/DH/DHS/EUR, spaces and non-breaking spaces, comma/period formatting, million(s), `M`, `mille` and `k`. Currency is preserved; EUR is not silently converted. Price on request, malformed values and per-m² values remain null with reasons. Monthly rent stays identifiable.

Surfaces are separated into total, built/habitable and land/terrain. Multiple unlabeled values generate a warning rather than being merged. Location aliases are conservative; ambiguous one-part locations preserve raw text and leave parsed fields null.

Validation is target-independent. Invalid examples include missing sale price and non-positive surfaces. Warnings include unknown transaction, extreme price/surface, inconsistent room counts and missing city. Records remain available for audit.

## Errors and resumption

Network and parsing errors include URL/card position in logs. Expected parser exceptions are caught per card with tracebacks; there is no broad silent `except`. Each successful page is appended immediately, so interruption preserves completed work. Restarting reloads known IDs.

## Tiny validation and Phase 5B gate

No live requests were performed in Phase 5A; validation used synthetic HTML and strings only (0 live listings). Before collecting 200–500 listings:

1. Obtain explicit approval for a maximum-20-listing technical check.
2. Review source access/automation constraints.
3. Verify current card selectors, pagination, canonical URL and native-ID coverage.
4. Determine whether detail pages may be accessed safely and which V2 fields are actually exposed.
5. Record parser coverage and fix any selector/schema mismatch.

Therefore: **PHASE 5B READY: NO** until these five checks pass. The code architecture and offline parsers are ready, but live source compatibility is deliberately unclaimed.

## Phase 5B pilot acceptance criteria

- 200–500 records maximum, isolated in `data/raw/maisonlux_listings_v2.csv`.
- Stable ID and raw URL preserved for 100% of accepted records; native/URL ID strategy ≥95%.
- Zero duplicate `listing_id` values.
- Zero known rent records in the sale subset; `UNKNOWN` excluded from training.
- ≥95% parsed price among records classified `SALE`.
- ≥90% usable city and ≥95% parsed property type.
- Surface coverage and correctness manually audited on at least 30 randomly selected pilot records; target ≥90% correct usable surface.
- Every parser failure has a status/reason and every request failure appears in logs; zero silent failures.
- Raw text retained for 100% of fields present at source.
- No pilot row enters the official training dataset without a separate review step.

## Connection to future model quality

**High value:** precise coordinates/address and quartier, land versus built surface, property condition, stable identity/deduplication, transaction type, listing date, and luxury characteristics. Phase 4.1 showed that 1% of test listings caused 64.87% of squared error and luxury listings 71.31%.

**Medium value:** floor/total floors, parking, elevator, terrace, garden, pool, views, security and furnished state—provided coverage is measured and unknown remains distinct from false.

**Lower or uncertain value:** sparse proximity phrases, fireplace, double glazing and title-deed wording. These may help particular segments but are too rare in the historical card text to promise a global gain.

No field guarantees a particular R². The purpose of V2 is to reduce label ambiguity and supply information the current API features cannot represent.
