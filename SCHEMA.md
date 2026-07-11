# Schema

Two entity types, one file each, validated against
[`schema/team.schema.json`](schema/team.schema.json) and
[`schema/kit.schema.json`](schema/kit.schema.json).

## Team

`data/teams/<sport>/<league|national>/<slug>.yaml`

| Field      | Req | Type            | Notes |
|------------|:---:|-----------------|-------|
| `slug`     |  ✓  | string          | `^[a-z0-9-]+$`, **must equal the file name**. German umlauts → `ae/oe/ue/ss`. |
| `name`     |  ✓  | string          | Canonical display name, e.g. `FC Bayern München`. |
| `sport`    |  ✓  | enum            | `football`, `basketball`, `american-football`, `ice-hockey`, `baseball`, `handball`, `rugby`. |
| `type`     |  ✓  | enum            | `club` or `national`. |
| `league`   |     | string \| null  | League slug (`bundesliga`, `nba`, …). `null` for national teams. |
| `country`  |     | string \| null  | ISO 3166-1 alpha-2, optionally with subdivision (`DE`, `GB-ENG`). |
| `aliases`  |     | string[]        | Spelling variants used by shops/feeds — drives name normalization. |
| `founded`  |     | integer \| null | |
| `logo_url` |     | string \| null  | Reference URL only; no image binaries are stored. |

The folder must match: `<sport>` = `sport`, and `<league|national>` = `league`
(clubs) or the literal `national` (national teams). CI enforces this.

## Kit

`data/kits/<sport>/<league|national>/<team-slug>/<season>-<kit_type>.yaml`

A *kit* is one jersey design = team + season + kit type (+ optional player edition).
Sizes/sleeve/gender are **not** modelled here — a kit just collects every known
GTIN for that design.

| Field          | Req | Type           | Notes |
|----------------|:---:|----------------|-------|
| `team`         |  ✓  | string         | Slug of an existing team (CI checks the reference). |
| `sport`        |  ✓  | enum           | Must match the team's `sport`. |
| `league`       |     | string \| null | |
| `season`       |  ✓  | string         | `YYYY/YY` (`2024/25`) or single year `YYYY` (`2024`) for tournaments. |
| `kit_type`     |  ✓  | enum           | `home`, `away`, `third`, `fourth`, `gk`, `training`, `special`. |
| `player_name`  |     | string \| null | Only for player-name editions. |
| `manufacturer` |     | string \| null | `adidas`, `Nike`, `Puma`, … |
| `main_sponsor` |     | string \| null | |
| `colorway`     |     | string \| null | Free-text, e.g. `Scarlet / Gold`. |
| `colors`       |     | string[] \| null | Primary colours of the design. **`colors[0]` is the shirt's base colour** — see below. |
| `gtins`        |     | string[]       | GTIN-8/12/13/14, **mod-10 check-digit validated**. The golden matching key. |
| `aliases`      |     | string[]       | Free-text product-name variants from shops. |
| `source`       |  ✓  | enum           | `manufacturer`, `feed`, or `community` (provenance). |
| `verified_by`  |     | string \| null | Required when `source = manufacturer`, e.g. `adidas`. |
| `notes`        |     | string \| null | |

### Colours

`colors` lists the colours of **this kit's design** — not the club's colour palette.

**`colors[0]` MUST be the base colour of the shirt itself**, i.e. the colour you see across most
of the jersey body. Trim, numbers, secondary and accent colours follow, in no particular order.

This ordering is load-bearing: consumers identify a kit by matching a shop's colour word
("white", "scarlet", "navy") against `colors[0]`. A palette dump breaks that. For example, the
New England Patriots' home shirt is nautical blue — so `colors[0]` is `Nautical Blue`, even
though white and silver appear on the shirt too, and even though the club's palette lists them
as club colours.

Leagues where the home shirt is *not* simply "the dark one" make this necessary: in the NFL the
home team picks its own shirt colour for the season and several teams traditionally wear white
at home; in MLB the home shirt is white and the road shirt is grey. There is no league-wide
rule to fall back on — the kit's own colours are the only reliable statement.

### GTINs

A GTIN is the barcode number on the packaging (EAN-13 is a GTIN-13). It is a
**public product identifier**, not commercial/affiliate data. Collect any you
can verify, even if you don't know which size a given code maps to — kit-level
is enough to match offers. Invalid check digits are rejected by `validate.py`.
