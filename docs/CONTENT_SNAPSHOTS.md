# Regional content snapshots (schema v1)

The content layer freezes exact revisions, validates availability/dependencies,
composes explicit Global previews and binds them to fixture scenarios. It does
not implement real heroes, combat formulas or neural learning.

## Complete local smoke run

```bash
python scripts/build_native.py
python scripts/smoke_regional.py --output runs/regional-001
```

This invokes the public CLI to build Global/CN snapshots and compose a preview,
replaces one fixture box entry with the explicitly imported synthetic candidate,
collects two baseline games, then runs a server and two external players as
separate processes. It verifies the resulting replays. Its dates and units are
artificial; results are not evidence about the Langrisser meta.

## Build and inspect snapshots

```bash
python -m apex_engine content build --catalog data/content/fixture_catalog.json \
  --manifest data/content/fixture_global_manifest.json --output runs/content/global.json
python -m apex_engine content build --catalog data/content/fixture_catalog.json \
  --manifest data/content/fixture_cn_manifest.json --output runs/content/cn.json
python -m apex_engine content preview --baseline runs/content/global.json \
  --source runs/content/cn.json --changes data/content/fixture_preview_changes.json \
  --snapshot-id fixture-global-preview --output runs/content/preview.json
python -m apex_engine content verify runs/content/preview.json
python -m apex_engine create --snapshot runs/content/global.json
python -m apex_engine selfplay --snapshot runs/content/preview.json \
  --episodes 2 --seed 1 --output runs/content-games-001
```

Output files and run directories must be new; old results are not overwritten.
Omit `--output` on build/preview to print the complete JSON. The tools never
download content or execute code from catalog records. The default scenario is
still the original unbound fixture; its hashes, protocol and behavior are unchanged.
Binding never strips an invalid snapshot or falls back to another region/version.

## Catalog and manifest

A catalog has `schema_version`, `catalog_id` and `entries`. Each entry has:

| Field | Meaning |
| --- | --- |
| `id`, `revision` | Stable, exact identifiers; no implicit latest revision |
| `kind` | hero, soldier, equipment, skill, map, mechanic, upgrade or draft |
| `fidelity` | `synthetic_fixture` or `release_metadata` in schema v1 |
| `mechanics` | Nonempty mechanic identifiers, not executable scripts |
| `dependencies` | Exact id/revision references, selected explicitly |
| `releases` | Both global and cn records; either can be null |
| `payload` | Synthetic JSON payload, or null for real release metadata |

Release records contain calendar dates `since`, `until`, `published_on` and a
`source`. Availability is `[since, until)`; null `until` means no recorded retirement.
A null regional record is unknown/unannounced, not a calculated future date.
Initial playable availability differs from current banner availability. A removed
mechanic revision may need a documented retirement date. Sources start with
`fixture:` for artificial data or public HTTPS for real release evidence. Source
contents are not fetched/verified by the loader; credibility is a data-review task.

A live manifest contains `schema_version`, `snapshot_id`, `mode`, `patch`, `as_of`,
`ruleset` and exact `entries` references. Modes are `global_live` or `cn_live`;
region is derived. The caller explicitly chooses its patch and revisions. The
system cannot infer missing patch corrections or undocumented retirements.

The builder rejects duplicate revisions, multiple active revisions per id,
unavailable entries, missing dependencies, cycles/dependency depth >64, malformed
fields and mixed fidelity. Selected entries are sorted deterministically.

## Seal and preview lineage

A snapshot embeds complete selected records and SHA-256 `content_digest`.
Verification checks its full body, schema, availability and dependencies. Hashes
detect inconsistency and pin content; they are not publisher signatures or proof
of game fidelity. Changed content gets a new digest. Conflicting definitions of
one id/revision across regional snapshots are rejected during composition.

`global_preview` requires a `global_live` baseline, a `cn_live` source and a nonempty
explicit changes list. Both inputs are embedded with their seals. The result
retains the baseline region, patch, date, ruleset and fidelity. Only named source
revisions are imported; all other baseline entries remain. Dependencies must
already exist or be explicitly imported. Overrides cannot silently update
dependents requiring the old revision. Nested previews, incompatible sources
and undeclared changes are rejected.

## Match binding and compatibility

`create --snapshot FILE` / `selfplay --snapshot FILE` attach a `content_snapshot`.
HTTP clients include that field in the existing scenario object. No server-side
catalog path is accepted; replays need no registry or original source files.

Before persistence every box hero must match the selected payload, and map/draft
payloads must match exactly. All included executable content must use supported
fixture mechanics, even unpicked candidates. Real release metadata cannot execute.

The complete snapshot participates in config/state hashes and is embedded in
the replay. Observations and collection reports expose an `experiment` label:
mode, region, patch/date, digest and preview provenance. The current fixture is
perfect-information; no real Apex information-access policy is claimed. Keep
these labels when comparing experiments.

## Real release evidence included

`release_evidence_catalog.json` has only D-Boy/Shinya Aiba initial release facts,
with official China and Global announcement URLs. Both records have null payloads
and unimplemented mechanic identifiers; they are not a complete regional roster.

```bash
python -m apex_engine content build --catalog data/content/release_evidence_catalog.json \
  --manifest data/content/release_evidence_global_manifest.json
```

This builds a `release_metadata` snapshot for historical 2026-08-13. It does not
assert the current full patch, playable loadout or hero strength. Verified game
content schemas and native mechanics must land before real matches are supported.
