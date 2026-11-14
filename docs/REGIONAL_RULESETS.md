# Global play and China-based forecasting

## Product decision

The owner plays on **Global**. Accurate Global Apex play is the primary target.
China is an advance research source and an additional evaluation environment.
The long-term goal includes testing upcoming heroes against the owner's Global
roster before their Global release.

Regional snapshot building, preview composition, availability/dependency validation
and fixture match binding are implemented. The only executable combat ruleset
remains `protocol-fixture-v0`; real Global/China gameplay is not supported yet.
See [content snapshot tooling](CONTENT_SNAPSHOTS.md) for the executable examples.

## Experiment modes

| Mode | Frozen environment | Intended question |
| --- | --- | --- |
| `global_live` | Selected, documented Global patch and content | What works in the supported current Global environment? |
| `cn_live` | Selected, documented China patch and content | What works in the supported China environment? |
| `global_preview` | Global baseline plus explicit China-derived candidate changes | How might these additions change my team and draft? |

These labels are accepted by snapshot manifests/builders, not bare scenario keys.
A scenario may carry an optional validated `content_snapshot`. Live means a
selected snapshot, not automatic remote tracking. Executable examples are synthetic.
Use one shared simulator with immutable, versioned regional bundles. Do not fork
an engine per region or use one mutable global hero table. Semantic differences
need a tested mechanic revision; an availability difference can reuse mechanics.

## Release timing

Do not implement `global_release = cn_release + 180 days`. Store release evidence
per region and leave unannounced dates unknown. An initial release announcement
does not establish a recurring banner schedule or universal future ordering.

Checked example, reviewed 2026-11-14:

- [Official China announcement](https://news.zlongame.com/jx/mzgg/20260325/26163.html):
  Tekkaman Blade update/event starts March 26, 2026.
- [Official Global announcement](https://us-news.zlongame.com/jx/mzInfoNewsEn/20260812/9794.html):
  the crossover update/event starts August 13, 2026.
- [Official Global follow-up](https://us-news.zlongame.com/jx/mzInfoNewsEn/20260817/9800.html)
  confirms the crossover went live August 13.

These calendar dates are 140 days apart, roughly 4.6 months. One example does not
establish an average delay or guarantee any future Global release. Distinguish
publication dates from effective game dates and retain original timezones.

## Required data and isolation

Future real-content schemas and experiment reports must include:

- Mode, region, effective patch, ruleset revision and immutable content digest.
- Map/draft format and supported loadouts. Stable ids with localized aliases;
  explicit revisions for forms, skills, soldiers, equipment and upgrades.
- Regional availability evidence, source, observed patch, confidence and a
  reproducible mechanic/interaction case. Announcements prove release facts,
  not combat timing or simulation fidelity.
- For previews, the baseline plus an exact list of additions/overrides and their
  dependencies. Do not implicitly import the entire future China environment.
- Policy/checkpoint, training environment, evaluation environment, seeds,
  first/second-player assignments and search/compute budget.

Global-live matches must reject unavailable content for their snapshot. Preview
matches explicitly permit declared candidate content; unsupported dependencies
block simulation with a named gap. Never approximate a real hero with fixture rules.
China observations inform hypotheses about Global behavior; verified transfer
of mechanics must be tracked separately from release availability.

Keep privileged state and observations separate in every mode. A China-trained
policy tested on Global receives Global's allowed observations/actions. Record
transfer evaluation explicitly and keep ratings from different modes distinct.

## What a useful preview should answer

Compare a Global roster before/after a declared candidate addition on the same
evaluation suite. Include fixed-team battles and draft outcomes, diverse opponents
and maps, comparable loadouts and both first/second-player assignments. Evaluate
multiple competent policies so poor use of a new mechanic is not mistaken for a
weak hero. Use held-out evaluation and uncertainty estimates.

Report matchup and ban/pick changes, synergy requirements, counterplay, unsupported
interactions and assumptions. A preview is a conditional simulation result, not
certainty about future human meta or a guaranteed purchase recommendation.

## Acceptance gates

1. Implemented: documentation and metadata distinguish synthetic and release data.
2. Implemented: snapshots reject regional leakage and missing dependencies; fixture
   matches bind exact content and preserve the snapshot in replay hashes.
3. Pending: real Global and China mechanics pass evidence-backed cases.
4. Pending: meaningful baseline/preview strength evaluation with competent learned
   policies and uncertainty estimates. Smoke games do not establish future meta.
