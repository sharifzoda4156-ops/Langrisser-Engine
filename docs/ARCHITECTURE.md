# Architecture

## Objective

A headless, evidence-backed Apex environment for battle/draft search, self-play
learning and independent human evaluation. Every player, including an external
LLM, must use the same decision contract and receive only permitted observations.

The owner's primary region is Global. China is an advance research and forecasting
source. Use shared engine code with frozen regional content/mechanic revisions;
see [regional rulesets](REGIONAL_RULESETS.md). Forecasts must name their Global
baseline and China-derived changes. Snapshot/data tooling and fixture binding are
implemented; real regional game mechanics are not. See [content snapshots](CONTENT_SNAPSHOTS.md).

## Executable foundation

The current stack is a vertical protocol fixture:

1. A strictly validated JSON scenario defines synthetic hero boxes and a map.
2. Python runs a synthetic ban/pick state machine and fixed deployment.
3. A C++20 executable enumerates legal battle actions and applies transitions.
4. The stand transactionally persists state and decision receipts in SQLite.
5. CLI/loopback HTTP clients request a decision and submit a legal action id.
6. Baseline runners finish games and export terminal-labelled trajectories.
7. Replay verification recomputes each transition and checks every event/hash.

This establishes a usable external-agent interface before actual game mechanics
land. It makes no claim of Langrisser fidelity, agent strength or training speed.

## Fixture semantics (not Apex rules)

- Two sides; 1–5 synthetic units per side; map dimensions 2–32 per axis.
- Terrain 0 is impassable; 1–9 is the entry cost; four-directional movement.
- Living units block transit and destination tiles, including allies.
- Dijkstra generates one deterministic shortest route per reachable endpoint.
  Paths include their starting tile; no route-dependent effects exist here.
- A unit may move then wait, or move then attack an enemy within Manhattan range.
- Damage is `min(target.hp, max(1, actor.attack - target.defense))`.
- No counterattack, soldiers, crits, line of sight, class bonuses or abilities.
- Acting marks that unit used; pass to the other side if it has a ready unit,
  otherwise retain the side that can still act. Each new round starts with side 0.
- Elimination wins; reaching the round limit with survivors on both sides draws.
- Synthetic draft: alternating bans against the other box, then alternating picks
  from one's own box. Already banned/picked heroes are excluded. This is not a
  claim about the actual Apex ban/pick schedule.
- Deployment places each side along its own map edge in pick order.

Unknown scenario keys and non-fixture ids are rejected so no unsupported mechanic
can be accidentally represented as a supported one.

## Native boundary

`build/apex_fixture legal|apply` reads a bounded whitespace integer protocol on
stdin and returns JSON on stdout. Text ids and storage never enter the native
parser. Native code validates dimensions, counts, unit records and action legality.
Python additionally validates the author-facing scenario schema.

Each call starts a native subprocess. This simple bridge is easy to exercise and
inspect but is intentionally NOT the final high-throughput training interface.
Profile representative workloads before adding bindings or persistent workers.
The simulator's semantic interface must stay usable without its UI or database.

## State, persistence and replays

`game.py` holds the logical draft/battle state. Configuration is immutable per
match. Canonical JSON hashes include the protocol, scenario and full logical state.
Identical fixture transitions produce identical hashes. Agent-side exploration
uses a separately seeded RNG; the synthetic environment has no randomness.

SQLite commits a decision receipt and its resulting match state in one transaction
under `BEGIN IMMEDIATE`. The receipt is keyed by a deterministic decision request
id and an exact submission. An identical retry returns the old receipt, even if
the match has since advanced. A changed retry is a conflict.

Replays contain the initial scenario and ordered submissions/receipts, plus the
final state and hash. Verification reconstructs the initial state and recomputes
all actions. It does not trust submitted final HP or copied event logs.
Hashes detect inconsistency; they are not signatures proving who authored a replay.

## Actual game mechanics

Create a new ruleset and verified scenario corpus before claiming real-game support.
Keep observations distinct from full state, chance outcomes explicit, and duration
clocks distinct (round, activation, action, combat, additional movement).
Implement hero/soldier effects, event priorities, snapshot/conversion rules,
damage timing, guard target selection and map effects from reproducible evidence.

Content can be data, reusable effects or reviewed code handlers. Build reusable
primitives from observed repetition; avoid an untested universal skill language.
Preserve patch/region and confidence for individual mechanics and interactions.

## Training and evaluation design

Planned: a battle policy/value model and search, followed by draft learning using
the battle policy's outcomes, then joint improvement against a league of past and
specialized opponents. Do not assume standard AlphaZero transfers unchanged to
stochastic or imperfect-information play. Do not alternate value signs blindly:
an extra action may leave the same player to move.

Training workers, policy weights, replay collection and evaluation are independent
processes. LLMs are optional players and debugging assistants, not automatic
weight updates. Train terminal objectives; validate any shaping against win rate.
Record ruleset, model, configuration, seed and search budget per experiment.
Promotion requires held-out tests, role-swapped comparisons and uncertainty
estimates. Human superiority requires a separate fair evaluation.

## Public information and private local configuration

AGENTS.md/CLAUDE.md are public developer instructions. Private per-machine notes
may use ignored AGENTS.local.md. Credentials belong in appropriate local secret
storage and never in repository instructions, replays or public experiments.
