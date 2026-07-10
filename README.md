# open-jersey-db

An **open, community-maintained database of football & team-sport jerseys** —
clubs, national teams, seasons, kit types, manufacturers, sponsors and the
**GTIN/EAN barcodes** that identify each shirt.

Think *MusicBrainz for jerseys*: a canonical identity layer that lets any
application recognise that "FC Bayern Heimtrikot 24/25", "Bayern Munich Home
Jersey 2024" and "adidas FCB H JSY" are the **same product** — and map shop
offers onto it by barcode. Because it's anchored to the authentic **GTIN/EAN**,
it also helps tell **genuine kits from counterfeits**.

Data is plain **YAML**, reviewed via pull requests, schema-validated in CI and
compiled to ready-to-consume **JSON** artifacts in [`dist/`](dist/).

## Why

Price-comparison and catalog apps all face the same problem: the same jersey
arrives from dozens of shops under wildly different names. The reliable key is
the **GTIN/EAN** printed on the packaging. This project collects that mapping
openly so nobody has to rebuild it privately.

### Helping spot counterfeits

There's a second reason this matters. The market is flooded with **fake-shop
counterfeits** of popular jerseys. An open, manufacturer-backed record of the
genuine products that actually exist — down to their authentic **GTIN/EAN** —
gives apps and buyers something to check against: a listing whose barcode,
season or kit doesn't match any known-genuine entry is a red flag.

open-jersey-db does **not** certify authenticity — only the brand can do that —
but it provides the **authentic-identity reference** that makes counterfeit
listings easier to catch. That is exactly why we invite **manufacturers and
brands** to contribute their authoritative data directly: the more complete the
genuine record, the harder it is for fakes to hide.

## Scope

Team- and club-sport jerseys across many leagues and countries — currently
**~350 teams and ~280 kits across 8 sports**:

- **Football (soccer)** — Bundesliga · 2. Bundesliga · 3. Liga · Regionalliga ·
  Premier League · La Liga · Serie A · Ligue 1 & 2 · MLS, plus national teams
- **American football** (NFL) · **Basketball** (NBA) · **Ice hockey** (NHL) ·
  **Baseball** (MLB)
- **Handball** and **rugby** (national teams) · **pro cycling** (Tour de France
  teams)

One schema covers them all — the `sport` and `league` fields carry the
distinction, so new sports and leagues arrive purely as data (PRs), no schema
change. **Metadata and barcodes only — no image binaries** (`logo_url` is a
reference, never a file).

## Structure

```
data/
  teams/<sport>/<league|national>/<slug>.yaml   # one team per file
  kits/<sport>/<league|national>/<team>/<season>-<kit_type>.yaml
schema/{team,kit}.schema.json                   # the contract (JSON Schema 2020-12)
dist/{teams,kits,aliases}.json                  # generated, committed artifacts
scripts/{validate,build}.py                     # gate + compiler (PyYAML only)
```

See [`SCHEMA.md`](SCHEMA.md) for every field.

## Consuming the data

Pin a release tag and read the JSON in `dist/`:

- `dist/teams.json` — all teams.
- `dist/kits.json` — all kits with their GTINs.
- `dist/aliases.json` — `{ "Canonical Name": ["alias", …] }`, a drop-in
  name-normalization map (e.g. for a price-comparison front end).

## Local development

```bash
python3 scripts/validate.py     # schema (if jsonschema installed) + integrity
python3 scripts/build.py        # regenerate dist/
```

`validate.py` needs only **PyYAML**; full JSON-Schema checking additionally uses
`jsonschema` (installed in CI). CI also asserts that `dist/` matches the source.

## Contributing

Everyone welcome — including **manufacturers**, who can submit authoritative kit
data and barcodes. See [`CONTRIBUTING.md`](CONTRIBUTING.md). By participating you
agree to our [Code of Conduct](CODE_OF_CONDUCT.md).

## Used by

- [**Trikot Scout**](https://trikotscout.com) — a jersey price-comparison site;
  the reference implementation that maps shop offers onto these identities.

Using open-jersey-db in your project? Open a PR to add it here.

## Citing

If you use this database in research or a product, please cite it. GitHub's
**“Cite this repository”** button (top-right) renders the entry in
[`CITATION.cff`](CITATION.cff) as APA or BibTeX. Attribution also satisfies the
ODbL license.

## License

Data is licensed under the **[Open Database License (ODbL) 1.0](LICENSE)** —
free to use and adapt **with attribution**, and derived databases must stay
open under the same terms.

## Notice & disclaimer

open-jersey-db is an **independent, fact-based** database. It records publicly
verifiable product-identity facts — team and kit names, seasons, manufacturers,
colours and **GTIN/EAN barcodes** — and deliberately contains **no prices,
offers, affiliate links, product images or personal data**.

- **Trademarks** — club, league and brand names (e.g. adidas, Nike, Puma, and
  the leagues) belong to their respective owners and are used here only
  *nominatively*, to identify products. This project is **not affiliated with,
  endorsed by, or sponsored by** any club, league, manufacturer or retailer.
- **GTIN/EAN** codes are public product identifiers issued by GS1 and are
  recorded as facts, for identification only.
- **Sources** — entries cite their primary source in the `source`/`notes`
  fields. Spotted a better or corrected attribution? Please open a PR.

### Reporting a rights or data concern

If you believe an entry infringes a right, is inaccurate, or should not be
published, please open an issue or email **info@dmnkrdr.com**. We review such
reports promptly and correct or remove data where warranted. For security
issues see [`SECURITY.md`](SECURITY.md).
