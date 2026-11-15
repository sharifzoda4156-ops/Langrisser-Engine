# Guard interception laboratory

`guard-lab-v1` extends the action lifecycle laboratory with a declared guard
configuration on each synthetic unit. `guard: null` disables protection;
otherwise `range` is 1..3 Manhattan tiles from the originally targeted ally
and `types` explicitly lists `physical` and/or `magic`. An attacker has
`attack_kind` and `ignore_guard`. The attack is chosen against the original
in-range target. An eligible living allied protector receives the synthetic
damage and emits `guard_intercept` before `fixture_damage`. The protector's
synthetic defense is used in the damage calculation. Its location and readiness
do not move or change merely because it protected an ally.

When several protectors are eligible, the laboratory selects the closest to the
protected unit, then the lowest unit ID. This selection order is a **laboratory
policy** and has not been verified in Global. Fixed damage, AoE, counterattack,
terrain bonus, simultaneous guards, disabled guard states and actual battle hit
ordering are outside the model. Physical and magic are explicit categories,
not inferred from classes or skills. The existing lifecycle and terrain rulesets
retain their frozen behavior and refuse guard fields.

A full tank can declare both types. A physical or magic specialist declares
only one. The example scenario now uses a dual-type protector; unit tests cover
all three configurations.

Official historical descriptions establish that guard may protect against
[both attack types or physical attacks at two tiles](https://us-news.zlongame.com/heroSSR/861.jhtml),
[magic attacks at two tiles](https://us-news.zlongame.com/heroSSR/1687.jhtml),
and that [Shadow Raid ignores Guard](https://us-news.zlongame.com/mzgl/1627.jhtml).
A generic 2019 guide describes only physical guarding, but skill-specific
magic guard exists. These references describe abilities, not independent proof
of current Global timing or tie-breaking. Global Battle Test observations are
still required, especially when multiple guards overlap or effects disable guard.

```bash
python scripts/build_native.py
python -m apex_engine selfplay --scenario scenarios/guard_lab.json --episodes 2 --seed 1 --output runs/guard-001
python -m apex_engine verify runs/guard-001/episode-00000.json
```
