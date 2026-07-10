# Contributing

Thanks for helping build an open jersey database! Contributions are plain YAML
files reviewed via pull request and checked automatically by CI. By taking part
you agree to our [Code of Conduct](CODE_OF_CONDUCT.md).

The database spans multiple team and club sports (football, American football,
basketball, ice hockey, baseball, handball, rugby and pro cycling) — the same
schema and workflow below apply to all of them.

## Quick start

1. Fork & branch.
2. Add or edit a YAML file under `data/` (see [`SCHEMA.md`](SCHEMA.md)).
3. Regenerate and validate:
   ```bash
   python3 scripts/build.py        # updates dist/
   python3 scripts/validate.py     # must pass
   ```
4. Commit **both** your `data/` change and the regenerated `dist/`.
5. Open a PR. CI re-validates the schema, integrity and that `dist/` is in sync.

> Only **PyYAML** is required to run the scripts; `pip install jsonschema`
> additionally enables full schema validation locally (CI always runs it).

## Adding a team

Create `data/teams/<sport>/<league|national>/<slug>.yaml`:

```yaml
slug: los-angeles-lakers      # == file name, [a-z0-9-]
name: Los Angeles Lakers
sport: basketball
type: club
league: nba
country: US
aliases: [lakers, la lakers, l a lakers]
```

National teams use `type: national`, `league: null`, and live under the
`national/` folder.

## Adding a kit

Create `data/kits/<sport>/<league|national>/<team-slug>/<season>-<kit_type>.yaml`:

```yaml
team: fc-bayern-muenchen      # must reference an existing team
sport: football
league: bundesliga
season: 2024/25               # or a single year, e.g. 2024
kit_type: home
manufacturer: adidas
main_sponsor: Deutsche Telekom
gtins:
  - "4067886123456"          # quote it — keep leading zeros, avoid number parsing
aliases: ["FCB Heimtrikot 24/25"]
source: community
```

`gtins` are mod-10 validated. Add only barcodes you can verify; kit-level
(any size) is enough.

## For manufacturers & brands 🏷️

You have the authoritative data — we'd love your help. Submit your official
kits and GTINs the same way (a YAML PR, no database access needed), and mark
provenance so users can trust verified entries:

```yaml
source: manufacturer
verified_by: adidas          # required when source = manufacturer
```

Verified entries are preferred over unverified community entries when data
conflicts. If a bulk import is easier for you, open an issue and we'll agree on
a format.

## Conventions

- **Quote GTINs and seasons** in YAML so they stay strings.
- Use the **canonical** team `name`; put every shop spelling into `aliases`.
- One logical change per PR keeps review fast.
- Data only — no copyrighted images. `logo_url` is a link, never a file.

## License

By contributing you agree your contribution is released under the project's
[ODbL 1.0](LICENSE).
