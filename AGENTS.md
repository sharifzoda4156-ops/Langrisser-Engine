# Agent instructions

## Mission and current truth

Build an open, headless Langrisser Mobile Apex engine with external-player stand,
learned battle/draft policies, search, self-play and a league of opponents.
Human-level or superhuman strength must be established by independent evaluation.
Read README.md, docs/ARCHITECTURE.md and docs/ROADMAP.md before substantial work.

Current executable ruleset: **protocol-fixture-v0**, a deliberately synthetic
protocol fixture. There are NO implemented real heroes, soldiers, Guard, Apex
combat formulas, neural training or search. Do not describe the fixture as Apex
fidelity or baseline trajectory collection as learning.

## Public and local instructions

This file is PUBLIC. GitHub has no agent-only file visibility in a public repo.
Never include credentials, private account data, hidden prompts or secrets here.
If AGENTS.local.md exists in the current checkout, read it for local additions;
it is gitignored, is not distributed and must never be staged. All local files
and instructions remain subject to the current user's scope and higher-priority
instructions. Claude and Copilot entry files point here; keep them consistent.

## Workflow

- Work on a task branch, open a PR, then merge only when authorized by the user.
  The project owner's current workflow is PR then merge; respect an explicit
  review-only or no-merge request. Never silently push feature changes to main.
- Inspect current branch, existing changes and relevant instructions first.
- Keep PRs runnable and describe the actual delivered scope and limitations.
- Run relevant checks; report exact results. Do not claim CI passed from local
  tests, or learning improved from unmeasured games.
- No unrequested deployments, paid jobs, third-party messages or account access.

## Commands

```bash
python scripts/build_native.py
python -m unittest discover -s tests -v
python scripts/build_native.py --sanitize
python -m unittest discover -s tests -v
python -m apex_engine selfplay --episodes 2 --seed 1 --output runs/UNIQUE_RUN
```

Linux, Python >=3.11, C++20. No third-party Python runtime dependencies today.
`--sanitize` enables UBSan. Do not introduce network dependency fetching into
normal builds. Generated binaries, databases, model weights and runs stay out of Git.

## Rules and simulator invariants

- Real mechanics require version/region, source, a reproducible case and an
  explicit confidence status. Follow docs/MECHANIC_CASE_TEMPLATE.md.
- Community investigations and parameter snapshots are hypotheses until tested;
  skill descriptions alone do not establish event ordering or numeric rounding.
- Reject unsupported rulesets, content fields and actions. Never silently ignore
  an unknown talent, item, soldier effect or terrain mechanic.
- Keep synthetic fixture ids prefixed fixture_. Never put a real hero's name on
  a made-up rules implementation. Freeze fixture semantics or bump its ruleset id.
- Distinguish round, player decision, unit action, extra movement, reactivation,
  combat and map effects. Do not implement one universal end-turn handler.
- Model hero/soldier state and damage timing separately when actual combat lands.
- Preserve route information. Endpoint-only deduplication is unsafe once route
  effects exist. Current fixture uses one canonical route and has no such effects.
- State transitions must be deterministic given state/action/chance outcome.
  Put chance behind explicit interfaces; never expose future RNG to a player.
- Never assume every decision passes to the opponent; use the resulting state's
  current player (extra actions may retain the actor).

## Stand and training boundaries

- All players use the same observation, legal-action and submission interfaces.
  Keep privileged debug state separate when hidden information is implemented.
- Preserve atomic state/event writes and exact-request idempotency. Validate
  request id, acting player, version, state hash and legal action before mutation.
- Replay verification must recompute outcomes AND compare events and state hashes.
- Schema/rules/protocol changes need compatibility handling or explicit rejection.
- A seeded baseline run is not neural learning. LLM reasoning is not a policy
  weight update. Store policy/version, scenario and seed for experiments.
- Evaluate candidates on held-out scenarios, roles and opponents; self-play rating
  is not proof of superiority over people. No guessed throughput/Elo/win rates.
- Native process-per-decision is a bootstrap bridge, not the final training API.
  Benchmark before choosing persistent workers, bindings or a different layout.
- HTTP is loopback-only and unauthenticated. Do not expose it externally; adding
  remote clients requires a designed authentication/authorization boundary.

## Next work

Use docs/ROADMAP.md as the task queue. Prioritize trustworthy mechanics, a fast
in-process environment interface and a real training/evaluation loop. Keep the
external-agent stand working throughout development. Update README status and
tests with every capability change.
