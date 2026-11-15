"""Compare two AoE terrain hypotheses against paired, controlled observations.

Research-only calculator models; neither model is an executable game ruleset.
"""

import argparse
from decimal import Decimal
import json
from pathlib import Path

from .errors import EngineError
from .formula_lab import fields, number


INPUT_FIELDS = {"attack", "hero_defense", "soldier_defense", "skill_multiplier",
                "terrain_percent", "max_error"}
CONTROL_FIELDS = {"same_units", "same_loadout", "ten_soldiers",
                  "no_tile_triggered_extras", "no_other_modifiers", "uncapped_hp",
                  "no_random_effects"}
OBSERVATION_FIELDS = {"plain", "terrain"}
POOL_FIELDS = {"hero", "soldier"}


def _damage(attack, defense, multiplier, terrain_percent):
    # Both published candidates use ten AoE contributions for each HP pool.
    return max(Decimal(0), attack - defense * (1 + terrain_percent / 100)) * multiplier * 10


def evaluate(case):
    fields(case, {"id", "region", "patch", "source", "input", "controls", "observed"}, "AoE case")
    if not isinstance(case["id"], str) or not case["id"].startswith("probe_"):
        raise EngineError("AoE case needs a probe_ identifier")
    if case["region"] not in ("China", "Global") or not isinstance(case["patch"], str) or not case["patch"].strip():
        raise EngineError("AoE case needs a region and patch")
    fields(case["input"], INPUT_FIELDS, "AoE input")
    values = {key: number(value, key) for key, value in case["input"].items()}
    attack, hero_def, soldier_def = (values[key] for key in ("attack", "hero_defense", "soldier_defense"))
    skill, terrain, error = (values[key] for key in ("skill_multiplier", "terrain_percent", "max_error"))
    if (min(attack, hero_def, soldier_def) < 0 or skill <= 0 or not 0 < terrain <= 100
            or not 0 <= error <= 10):
        raise EngineError("invalid AoE stat, skill, terrain or error bound")
    if max(hero_def, soldier_def) == 0 or all(attack <= d for d in (hero_def, soldier_def)):
        raise EngineError("case cannot distinguish terrain defense on either HP pool")
    fields(case["controls"], CONTROL_FIELDS, "AoE controls")
    if any(type(flag) is not bool for flag in case["controls"].values()):
        raise EngineError("AoE controls must be booleans")

    plain = {pool: _damage(attack, defense, skill, Decimal(0))
             for pool, defense in (("hero", hero_def), ("soldier", soldier_def))}
    with_terrain = {pool: _damage(attack, defense, skill, terrain)
                    for pool, defense in (("hero", hero_def), ("soldier", soldier_def))}
    predictions = {"plain": plain, "no_terrain": plain, "with_terrain": with_terrain}
    report = {"id": case["id"], "region": case["region"], "patch": case["patch"],
              "source": case["source"], "fidelity": "research_probe", "predictions":
              {label: {pool: str(value) for pool, value in amounts.items()}
               for label, amounts in predictions.items()}}
    observed = case["observed"]
    if observed is None:
        if case["source"] != "unmeasured":
            raise EngineError("unmeasured AoE case must have source 'unmeasured'")
        report["result"] = "awaiting_observation"
        return report
    if not isinstance(case["source"], str) or not case["source"].startswith("https://"):
        raise EngineError("measured AoE case needs a source URL")
    fields(observed, OBSERVATION_FIELDS, "AoE observation")
    measurements = {}
    for location in OBSERVATION_FIELDS:
        fields(observed[location], POOL_FIELDS, f"AoE {location} losses")
        measurements[location] = {pool: number(amount, pool)
                                  for pool, amount in observed[location].items()}
        if min(measurements[location].values()) < 0:
            raise EngineError("negative observed HP loss")
    report["observed"] = {location: {pool: str(value) for pool, value in amounts.items()}
                          for location, amounts in measurements.items()}
    report["max_error"] = str(error)
    report["absolute_error"] = {
        "plain": {pool: str(abs(measurements["plain"][pool] - plain[pool])) for pool in POOL_FIELDS},
        "no_terrain": {pool: str(abs(measurements["terrain"][pool] - plain[pool])) for pool in POOL_FIELDS},
        "with_terrain": {pool: str(abs(measurements["terrain"][pool] - with_terrain[pool])) for pool in POOL_FIELDS},
    }
    if not all(case["controls"].values()):
        report["result"] = "uncontrolled"
        return report
    if any(abs(measurements["plain"][pool] - plain[pool]) > error for pool in POOL_FIELDS):
        report["result"] = "baseline_mismatch"
        return report
    matches = {"no_terrain": all(abs(measurements["terrain"][pool] - plain[pool]) <= error
                                 for pool in POOL_FIELDS),
               "with_terrain": all(abs(measurements["terrain"][pool] - with_terrain[pool]) <= error
                                   for pool in POOL_FIELDS)}
    report["result"] = ("supports_terrain" if matches["with_terrain"] and not matches["no_terrain"]
                        else "supports_no_terrain" if matches["no_terrain"] and not matches["with_terrain"]
                        else "inconclusive")
    return report


def check_cases(path):
    payload = json.loads(Path(path).read_text())
    fields(payload, {"schema", "cases"}, "AoE case file")
    if payload["schema"] != "aoe-terrain-probe-v1" or not isinstance(payload["cases"], list) or not payload["cases"]:
        raise EngineError("unsupported or empty AoE case file")
    reports = [evaluate(case) for case in payload["cases"]]
    if len({report["id"] for report in reports}) != len(reports):
        raise EngineError("duplicate AoE case id")
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_file")
    args = parser.parse_args()
    try:
        print(json.dumps({"fidelity": "research_probe", "cases": check_cases(args.case_file)}, indent=2))
    except (EngineError, OSError, ValueError, TypeError) as error:
        parser.exit(2, f"AoE probe failed: {error}\n")


if __name__ == "__main__":
    main()
