# Terrain profile laboratory

`terrain-lab-v1` extends the lifecycle lab with explicit per-unit movement
profiles. It remains `mechanics_lab`; damage and unit identities are synthetic.
The `costs` grid contains only 0 (impassable to all) and 1 (passable); each
`terrain` cell has a fixture identifier and each `profiles` mapping provides a
positive movement cost for every terrain identifier. Units explicitly choose a
profile. Inherited mobility is the minimum of hero and soldier mobility values.
The native pathfinder calculates one least-cost route per endpoint. Profiles also
apply to post-attack movement. Unknown profiles or missing costs are rejected.

The [official Global terrain guide](https://us-news.zlongame.com/mzgl/995.jhtml)
describes a desert example: cavalry spends two mobility per square, infantry and
fliers are unaffected. The example scenario encodes these three cases with
explicit profiles. The article is historical; this project has not independently
verified current Global gameplay. These values are not a complete terrain table.

The lab does not infer profile from hero and soldier classes or model movement
exceptions, impassable terrain by individual profile, movement through allies,
route-triggered effects, terrain defense, guard, or actual Apex maps. A shared
passability grid and one route per endpoint are lab restrictions. Use Global Battle
Test to record game version, hero class, soldier type, loadout, tiles and observed
reachable squares before applying any profile to real content.

```bash
python scripts/build_native.py
python -m apex_engine selfplay --scenario scenarios/terrain_lab.json --episodes 2 --seed 1 --output runs/terrain-001
python -m apex_engine verify runs/terrain-001/episode-00000.json
```
