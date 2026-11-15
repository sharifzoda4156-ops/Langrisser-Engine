# Chinese formula research and calculator probes

The executable `apex_engine.formula_lab` is a **research_probe**, deliberately
not wired into battle transitions. Run:

```bash
python -m apex_engine.formula_lab data/mechanics/formula_research_cases.json
```

Its JSON file records four narrow observations. It verifies equality with
exact Decimal arithmetic rather than silently accepting a tolerance. A passing
probe shows agreement with the *stated inputs of a calculator*, not with live
Global combat. Inputs are already selected attack/defense panels, so the
calculator cannot validate the equipment build that produced them.

| Probe | Input | Calculator or source result |
| --- | --- | --- |
| Panel composition | white 1000, flat equipment 100, flat enchant 20, enchant 5%, set 5%, battle 25% | panel 1220, battle 1525 (formula example from community analysis) |
| Base strike | attack 1000, defense 400, skill ×1 | 300 per strike, 6000 / 20 strikes, crit 7800 |
| Distinct damage groups | base + general 20%, skill 10% | 396 per strike, 7920 total |
| Defense modifiers | previous + defense 20%, ignore defense 20% | adjusted defense 384, 406.56 per strike, 8131.2 total |

The observed damage groups multiply across categories. Defense class and
terrain percentages are additive *within the defense coefficient*, then
multiplied by the remaining defense after ignore. Physical/magic inputs must be
selected explicitly by caller; this probe has no class or skill inference.
Critical output assumes the calculator's 30% baseline but **does not model
critical probability**. Fractional outputs are retained: exact game rounding
per hit, animation order and overkill are not established here. A simple
20-strike sum cannot predict kills when hero and soldiers strike independently.

Sources and status:

- [Moyuan calculator](https://moyuanmzjsq.streamlit.app/): directly checked on
  2026-11-15 with the numeric inputs above. Its description advises using it
  to test mechanics rather than promising actual match outcomes.
- [Chinese community analysis](https://wiki.biligame.com/langrisser/梦战基础数据分析),
  updated 2020: white/flat/enchantment grouping and separate 20-hit hero and
  soldier contributions. It explicitly leaves some rules unverified.
- [Official China enchant overview](https://news.zlongame.com/jx/sysmz/20180619/5180.html):
  equipment slots and set effects. The 2018 Sun four-piece value differs from
  a later community table; never hard-code a timeless set bonus.
- [Moyuan's S26 terrain test](https://moyuanlab.com/langrisser/guide-2e92b3b2b0f3/):
  terrain affects both defense types and soldiers, remains outside visible panel,
  and a guarding tank uses the protected unit's terrain. The existing guard lab
  does **not** model this yet.
- [Soldier-stat analysis](https://www.3loumao.org/18905.html), 2021:
  level, barracks, faction and covenant terms with a warning that its boss
  estimates do not directly generalize to PvP.

Next validation needs actual Global Battle Test screenshots or recordings with
patch, hero and soldier stats, equipment and enchant rolls, terrain, prebattle
buffs, both HP pools and the per-hit sequence. Compare each rounding point and
source of damage separately; keep historical China findings tagged by season.
