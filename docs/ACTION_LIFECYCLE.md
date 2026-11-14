# Action lifecycle laboratory v1

`action-lifecycle-lab-v1` exercises a separate lifecycle over synthetic units and
damage. Its fidelity is **mechanics_lab**, not current-patch Apex. It introduces
source-backed distinctions without claiming that every selected timer/scheduler
policy matches Global. Actual heroes, guard, skill damage, soldiers' HP and
passives are still unsupported. Names remain `fixture_` identifiers.

## What works

- Separate activation and action counters, unit readiness and round boundaries.
- Immediate self continuation, ally reactivation and movement-only continuation.
- No opponent decision while an immediate continuation or post-move is pending.
- Movement budget limited by the slower hero/soldier base mobility component.
- Explicit owner-action-end and round-end effect clocks, first-tick policy,
  optional per-skill preservation of owner-action effect durations and cooldowns.
- Stand persistence/restart during pending decisions, deterministic replay and
  baseline collection using the same interfaces as the original fixture.

```bash
python scripts/build_native.py
python -m apex_engine selfplay --scenario scenarios/action_lifecycle_lab.json \
  --episodes 2 --seed 1 --output runs/lifecycle-001
python -m apex_engine verify runs/lifecycle-001/episode-00000.json
python scripts/smoke_external.py --scenario scenarios/action_lifecycle_lab.json \
  --output runs/lifecycle-external-001
```

The existing `protocol-fixture-v0` remains unchanged. Its original scenarios,
regional content bindings and replay hashes do not migrate to the laboratory.
Snapshot binding is rejected for this lab until its content schema is implemented.

## Event contract and laboratory policies

An activation starts when a ready unit is chosen. Each full action emits
`action_start` and exactly one `action_end`. An immediate self refresh keeps that
unit and activation selected but grants a new full action. Ally refresh marks an
already-used friendly unit ready; normal handoff follows the caster's completion.
The lab does not permit refreshing oneself or an already-ready ally.

After an attack, `post_move_start` may open a decision restricted to `finish_move`
for that unit. It permits declining movement by choosing its current tile; it
does not grant an attack or skill cast. The lab defers action-end processing until
`post_move_end`, then closes that action once. Exact real-game callback/duration
timing during post-move remains a hypothesis requiring controlled observations.

Owner timers tick only on the owner's completed full action; round timers tick
after all living units finish their actions and pending movement. Initial effects
and skill-applied effects explicitly select `current_boundary` or
`following_boundary` for their first tick. Same-id reapplication replaces a timer;
effects in this lab are markers and **do not change combat statistics**.

New cooldowns skip the cast's own completion boundary, then decrease on subsequent
owner action ends. A skill can explicitly preserve owner-action effect durations
for its completion; cooldown counters remain separate. These are declared lab
policies, not a universal claim about every Langrisser ability.

Each lab skill declares a finite uses-per-round limit. Together with a round
limit this provides a provable decision bound. It is not an Apex cap on extra
actions. New rounds start with the configured `first_player`. At round limit the
lab draws; it does not implement Apex damage-based tiebreaks, poison or current
map rules. Elimination ends a lab match without a needless post-move prompt.

The C++ `resolve` command executes only weighted movement/synthetic damage;
Python owns lifecycle boundaries. Legacy native `apply` retains its original
scheduling and exact event output. Native results never overwrite lab timers,
skills or readiness. This remains a bootstrap process bridge, not a speed claim.

## Evidence, scope and unresolved cases

Sources inspected 2026-11-14. These are documented contracts, not observations
from this project's own game client. Detailed records are in
[the evidence inventory](../data/mechanics/action_lifecycle_evidence.json).

| Concept | Primary evidence | Implemented scope / limitation |
| --- | --- | --- |
| Unit mobility | [Global official guide, 2019](https://us-news.zlongame.com/mzgl/994.jhtml) | Minimum of base hero/soldier mobility; no auras, special profiles or new patch certification |
| Extra movement versus another action | [Official Leon card, China](https://news.zlongame.com/jx/heroSSR/20180619/5173.html) | Separate post-move and self-refresh primitives; not a full Leon/Chivalry implementation |
| Duration preservation can be skill-specific | [Global official Transcender description, 2021](https://us-news.zlongame.com/jx/mzInfoNewsEn/20211115/7905.html) | Explicit preservation option; HP exchange and other hero behavior are not implemented |
| Multiple actions within a round | [Global official Cherie guide, 2019](https://us-news.zlongame.com/mzgl/1701.jhtml) | Distinct action/round clocks; Cherie's kill trigger is not implemented |
| Reproducible real-game testing | [Global Battle Test announcement, 2025](https://us-news.zlongame.com/jx/mzInfoNewsEn/20250810/9690.html) | Both teams can be controlled using account-owned content; no live account session is connected here |

The old mobility article also makes an overbroad physical-only Guard statement;
that claim is NOT adopted as a universal rule. A historical China announcement
[changed Apex's 12-round tiebreak](https://news.zlongame.com/jx/mzInfoNews/20191106/11175.html)
to damage-based comparison. This is why an old secondary description cannot
establish current Global adjudication; the lab's draw is explicitly artificial.

## Global observation checklist

In Arena → Battle Test, record the exact map, patch, classes, soldiers, loadouts,
HP, effects, cooldowns, actions and first/second-player assignment. Account-owned
content limits the available experiments. Do not treat setting up this laboratory
as having run any of these game-client tests.

1. On flat terrain with no modifiers, compare hero mobility 5 paired with soldier
   mobility 3 versus 5, and record the actual movement budget.
2. Record an existing short-duration buff before/after a self-refresh ability,
   then after its subsequent action. Compare a preservation-labelled ability.
3. For post-attack movement, capture cooldown/effect counters before attacking,
   during the movement prompt and after confirming/declining it.
4. Cast an ally refresh on an already-used unit; record readiness and which side
   may choose the next unit. Test inability to target a ready/self unit separately.
5. Record a newly cast skill's cooldown across its cast, continuation and next
   round. Determine which exact boundary ticks it instead of guessing from text.

Current-Global confirmation of scheduling, duration defaults, cooldown first tick,
reapplication, blocking effects and interaction ordering remains pending. Verified
data can later select rule-specific handlers without collapsing these boundaries.
