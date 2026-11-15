# Roadmap

Goal: a self-improving Apex draft/battle agent with verifiable mechanics and fair
evaluation against strong people. No fixed date, throughput or strength promise.

Primary target: **Global**. China supplies advance research and explicit Global
preview experiments. See [regional rulesets and forecasting](REGIONAL_RULESETS.md).
Release delays are evidence per content item, not a fixed six-month rule.

## M0 — Executable foundation (this version)

- [x] Synthetic draft/battle fixture in a native C++ core + Python stand.
- [x] External player request/action contract over CLI and loopback HTTP.
- [x] Durable state, atomic receipts and concurrent retry protection.
- [x] Deterministic replay verification, baseline self-play and trajectory export.
- [x] Agent instructions, contribution workflow and CI.

Acceptance: external processes complete a fixture game, duplicate/stale decisions
are handled correctly, restart preserves state and all replays verify.

## M1 — Verified rules and native environment interface

- [x] Choose Global as the primary region and China as an advance research source.
- [ ] Freeze the initial Global patch, actual Apex format, one map and fixed loadouts.
- [x] Add sealed regional snapshots, availability/dependency validation and explicit
  Global previews; bind supported snapshots to fixture matches and replay hashes.
- [ ] Populate verified real-game regional content and implement its mechanics;
  metadata-only release records do not count as playable heroes.
- [x] Start a primary-source mechanics inventory with explicit unknowns and lab probes.
- [x] Model separate rounds, activations, actions, immediate continuations, ally
  reactivation, post-move and explicit effect clocks in action-lifecycle-lab-v1.
- [ ] Confirm the laboratory policies in current Global Battle Test and map actual
  hero/skill handlers; do not treat documented contracts as gameplay verification.
- [x] Add a versioned synthetic terrain-profile laboratory with per-unit costs.
- [x] Add an explicit synthetic physical/magic Guard interception laboratory.
- [ ] Validate actual movement profiles, terrain effects and guard timing in Global.
- [x] Add a synthetic guard plus hero/soldier HP accounting laboratory.
- [ ] Validate actual soldier/hero hit timing, crits, stat conversions and rounding.
- [ ] Explicit chance/observation interfaces; no RNG or privileged-state leakage.
- [ ] Add a small validated roster covering the required interactions.
- [ ] Benchmark and add an efficient in-process training interface.

Acceptance: held-out real-game cases match documented tolerances and event order;
unsupported loadouts fail explicitly. Fixture results do not count as game fidelity.

## M2 — Learned battle agent

- [ ] Define encoded observations and legal-action masks/representations.
- [ ] Implement actual model training and save/load checkpoints.
- [ ] Compare policy-only, search-only and policy+search baselines.
- [ ] Handle chance and same-player extra decisions correctly in search/returns.
- [ ] Maintain a league, held-out scenarios, role-swapped evaluation and run metadata.
- [ ] Measure strength and throughput, including inference, search and collection.

Acceptance: measured improvement over fixed baselines and previous versions on
held-out tests, with reproducible checkpoints. More games alone is not acceptance.

## M3 — Learned draft and joint improvement

- [ ] Implement the selected real ban/pick schedule and loadout/deployment choices.
- [ ] Train draft decisions against sufficiently competent battle policies.
- [ ] Evaluate final battle outcomes, not standalone hero ratings.
- [ ] Jointly improve draft and battle against diverse league opponents.
- [ ] Expand scenarios and loadouts without silently resetting old evaluations.
- [ ] Compare an owner's Global roster before/after declared China-derived additions;
  include dependency checks, regional availability and uncertainty estimates.

## M4 — Usable analysis and human evaluation

- [ ] Browser board/replay viewer and position import/export.
- [ ] Best-action candidates with lines, assumptions and computation budget.
- [ ] Independent match series against strong players under comparable conditions.
- [ ] Confidence estimates and documented limitations per supported ruleset.

Training and UI may develop alongside the simulator, but no strength claim may
outrun evidence that the simulator implements the evaluated game.
