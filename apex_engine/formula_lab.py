"""Exact-decimal research probes; never used as the live battle ruleset."""
import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

from .errors import EngineError


STAT_FIELDS = {"white", "equipment_flat", "enchant_flat", "enchant_percent",
               "set_percent", "battle_percent"}
DAMAGE_FIELDS = {"attack_class_percent", "defense_class_percent", "terrain_percent",
                 "ignore_defense_percent", "skill_multiplier", "strike_coefficient",
                 "strikes", "general_damage_percent", "skill_damage_percent",
                 "ranged_damage_percent", "other_damage_percent",
                 "critical_bonus_percent", "critical_reduction_percent"}


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise EngineError(f"{name} must be an integer or decimal string")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise EngineError(f"invalid {name}") from error
    if not result.is_finite() or abs(result) > 1000000:
        raise EngineError(f"{name} outside probe limits")
    return result


def fields(value, required, name):
    if not isinstance(value, dict) or set(value) != required:
        raise EngineError(f"{name} requires exactly: {', '.join(sorted(required))}")


def percent(value):
    return Decimal(1) + value / 100


def stat(spec):
    """Research hypothesis for one stat, not an authenticated game formula."""
    fields(spec, STAT_FIELDS, "stat")
    v = {key: number(value, key) for key, value in spec.items()}
    if v["white"] < 0 or v["equipment_flat"] < 0 or v["enchant_flat"] < 0:
        raise EngineError("negative base or flat stat")
    panel = v["white"] * percent(v["enchant_percent"] + v["set_percent"])
    panel += v["equipment_flat"] + v["enchant_flat"]
    battle = panel * percent(v["battle_percent"])
    if min(panel, battle) < 0:
        raise EngineError("negative stat")
    return {"panel": panel, "battle": battle}


def damage(attacker, defender, spec):
    """Calculator cross-check for a single attacker/defender stat pair."""
    fields(spec, DAMAGE_FIELDS, "damage")
    a, d = number(attacker, "attacker"), number(defender, "defender")
    v = {key: number(value, key) for key, value in spec.items()}
    if a < 0 or d < 0 or v["skill_multiplier"] <= 0 or v["strike_coefficient"] <= 0:
        raise EngineError("invalid attack, defense or strike multiplier")
    if v["strikes"] != int(v["strikes"]) or not 1 <= v["strikes"] <= 40:
        raise EngineError("strikes must be 1..40")
    if not 0 <= v["ignore_defense_percent"] <= 100:
        raise EngineError("ignore defense must be 0..100 percent")
    adjusted_attack = a * percent(v["attack_class_percent"])
    adjusted_defense = d * percent(v["defense_class_percent"] + v["terrain_percent"])
    adjusted_defense *= percent(-v["ignore_defense_percent"])
    if min(adjusted_attack, adjusted_defense) < 0:
        raise EngineError("negative adjusted stat")
    each = max(Decimal(0), adjusted_attack - adjusted_defense)
    each *= v["skill_multiplier"] * v["strike_coefficient"]
    for key in ("general_damage_percent", "skill_damage_percent",
                "ranged_damage_percent", "other_damage_percent"):
        if percent(v[key]) < 0:
            raise EngineError("negative damage group")
        each *= percent(v[key])
    critical = percent(Decimal(30) + v["critical_bonus_percent"]
                       - v["critical_reduction_percent"])
    if critical < 0:
        raise EngineError("negative critical multiplier")
    return {"adjusted_attack": adjusted_attack, "adjusted_defense": adjusted_defense,
            "per_strike": each, "total": each * v["strikes"],
            "critical_per_strike": each * critical, "critical_total": each * critical * v["strikes"]}


def check_cases(path):
    payload = json.loads(Path(path).read_text())
    fields(payload, {"schema", "cases"}, "case file")
    if payload["schema"] != "formula-research-v1" or not isinstance(payload["cases"], list) or not payload["cases"]:
        raise EngineError("unsupported or empty formula case file")
    reports = []
    for case in payload["cases"]:
        fields(case, {"id", "source", "kind", "input", "expected"}, "case")
        if not isinstance(case["id"], str) or not case["id"].startswith("probe_"):
            raise EngineError("cases need probe_ identifiers")
        if not isinstance(case["source"], str) or not case["source"].startswith("https://"):
            raise EngineError("case needs a source URL")
        if case["kind"] == "stat":
            actual = stat(case["input"])
        elif case["kind"] == "damage":
            fields(case["input"], {"attacker", "defender", "modifiers"}, "damage input")
            actual = damage(case["input"]["attacker"], case["input"]["defender"], case["input"]["modifiers"])
        else:
            raise EngineError("unsupported case kind")
        if not isinstance(case["expected"], dict) or not case["expected"] or not set(case["expected"]) <= set(actual):
            raise EngineError("invalid expected values")
        for key, expected in case["expected"].items():
            if actual[key] != number(expected, key):
                raise EngineError(f"case {case['id']} mismatch for {key}: got {actual[key]}, expected {expected}")
        reports.append({"id": case["id"], "checked": list(case["expected"]), "matched": True})
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_file")
    args = parser.parse_args()
    try:
        print(json.dumps({"fidelity": "research_probe", "cases": check_cases(args.case_file)}, indent=2))
    except (EngineError, OSError, ValueError) as error:
        parser.exit(2, f"research probe failed: {error}\n")


if __name__ == "__main__":
    main()
