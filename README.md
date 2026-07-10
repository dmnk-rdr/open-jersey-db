# open-jersey-db

An **open, community-maintained database of football & team-sport jerseys** —
clubs, national teams, seasons, kit types, manufacturers, sponsors and the
**GTIN/EAN barcodes** that identify each shirt.

Think *MusicBrainz for jerseys*: a canonical identity layer that lets any
application recognise that "FC Bayern Heimtrikot 24/25", "Bayern Munich Home
Jersey 2024" and "adidas FCB H JSY" are the **same product** — and map shop
offers onto it by barcode.

Data is plain **YAML**, reviewed via pull requests, schema-validated in CI and
compiled to ready-to-consume **JSON** artifacts in [`dist/`](dist/).

## Why

Price-comparison and catalog apps all face the same problem: the same jersey
arrives from dozens of shops under wildly different names. The reliable key is
the **GTIN/EAN** printed on the packaging. This project collects that mapping
openly so nobody has to rebuild it privately.

## Scope

Team-sport jerseys across leagues — football today, with room for basketball
(NBA), American football (NFL) and ice hockey (NHL): the `sport` and `league`
fields carry that distinction, the schema stays the same. **Metadata and
barcodes only — no image binaries** (`logo_url` is a reference, never a file).

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
