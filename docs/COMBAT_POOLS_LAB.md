# Hero and soldier health pool laboratory

`combat-pools-lab-v1` combines the explicit physical/magic guard selector with
separate hero and soldier health counters. Every fixture unit declares `hero_hp`,
`soldier_hp`, and their sum `hp`. A single synthetic strike first depletes the
soldier pool; overflow reduces hero health. The existing synthetic damage amount
is `max(1, attack - defense)` capped by total remaining health. Events include
`guard_intercept` (if any), `fixture_damage_pools` and `fixture_damage`. Native
movement resolves before the Python laboratory allocates damage; state and replay
include both counters, so the stand can verify the exact transition.

This is a *single deterministic accounting probe*, not a Langrisser combat
formula. It does not implement soldier count, 20-hit sequences, hero/soldier
attack order, crit chance, terrain defenses, damage modifiers, counterattacks,
magic defense, healing, resurrection or real hero skills. Only declared
physical/magic attack tags select a protector; full guard declares both tags,
while a specialist declares one. Multiple eligible guards still use the
laboratory priority described in [Guard lab](GUARD_LAB.md). Real battle damage
and timing need independently recorded cases from Global Battle Test.

```bash
python scripts/build_native.py
python -m apex_engine selfplay --scenario scenarios/combat_pools_lab.json --episodes 2 --seed 1 --output runs/combat-pools-001
python -m apex_engine verify runs/combat-pools-001/episode-00000.json
```
