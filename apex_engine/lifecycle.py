"""Action lifecycle laboratory, not a full or current-patch Apex implementation.

Documented game concepts are separated from declared laboratory clock/scheduler
policies. Damage remains synthetic. See docs/ACTION_LIFECYCLE.md for evidence.
"""
import copy
import re

from .errors import EngineError
from .schema import digest, integer, keys

RULESET = "action-lifecycle-lab-v1"
CLOCKS = ("owner_action_end", "round_end")
SKILL_KINDS = ("self_refresh", "ally_refresh", "timed_effect")


def fixture_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"fixture_[a-z0-9_]{1,70}", value):
        raise EngineError("laboratory names must be fixture_ identifiers")
    return value


def effect_definition(effect):
    keys(effect, ["id", "clock", "remaining", "first_tick"], "lab effect")
    fixture_id(effect["id"])
    if effect["clock"] not in CLOCKS or effect["first_tick"] not in ("current_boundary", "following_boundary"):
        raise EngineError("effect requires an explicit supported clock and first_tick policy")
    integer(effect["remaining"], "effect duration", 1, 20)


def validate_config(config):
    keys(config, ["ruleset", "map", "round_limit", "first_player", "units"], "lifecycle scenario")
    if config["ruleset"] != RULESET:
        raise EngineError("unsupported lifecycle ruleset")
    board = config["map"]
    keys(board, ["width", "height", "costs"], "map")
    width = integer(board["width"], "width", 2, 32)
    height = integer(board["height"], "height", 2, 32)
    if not isinstance(board["costs"], list) or len(board["costs"]) != width * height:
        raise EngineError("invalid laboratory map costs")
    for cost in board["costs"]:
        integer(cost, "terrain cost", 0, 9)
    integer(config["round_limit"], "round_limit", 1, 100)
    integer(config["first_player"], "first_player", 0, 1)
    units = config["units"]
    if not isinstance(units, list) or not 2 <= len(units) <= 10:
        raise EngineError("laboratory needs 2..10 units")
    ids, positions, owners = set(), set(), [0, 0]
    for unit in units:
        keys(unit, ["id", "name", "owner", "x", "y", "hp", "attack", "defense",
                    "hero_movement", "soldier_movement", "range", "post_attack_move",
                    "skills", "effects"], "lab unit")
        fixture_id(unit["name"])
        for field, low, high in [("id", 0, 99), ("owner", 0, 1), ("x", 0, width - 1),
                                 ("y", 0, height - 1), ("hp", 1, 10000), ("attack", 1, 10000),
                                 ("defense", 0, 10000), ("hero_movement", 0, 10),
                                 ("soldier_movement", 0, 10), ("range", 1, 10),
                                 ("post_attack_move", 0, 10)]:
            integer(unit[field], field, low, high)
        position = (unit["x"], unit["y"])
        if unit["id"] in ids or position in positions or board["costs"][unit["y"] * width + unit["x"]] == 0:
            raise EngineError("duplicate unit/position or blocked deployment")
        ids.add(unit["id"])
        positions.add(position)
        owners[unit["owner"]] += 1
        if not isinstance(unit["effects"], list) or len(unit["effects"]) > 10:
            raise EngineError("at most 10 initial effects per unit")
        effect_ids = set()
        for effect in unit["effects"]:
            effect_definition(effect)
            if effect["id"] in effect_ids:
                raise EngineError("duplicate initial effect id")
            effect_ids.add(effect["id"])
        if not isinstance(unit["skills"], list) or len(unit["skills"]) > 3:
            raise EngineError("at most 3 lab skills per unit")
        skill_ids = set()
        for skill in unit["skills"]:
            keys(skill, ["id", "kind", "cooldown", "range", "move_allowance", "preserve_effects",
                         "uses_per_round", "effect"], "lab skill")
            fixture_id(skill["id"])
            if skill["id"] in skill_ids or skill["kind"] not in SKILL_KINDS:
                raise EngineError("duplicate skill or unsupported skill kind")
            skill_ids.add(skill["id"])
            integer(skill["cooldown"], "cooldown", 1, 10)
            integer(skill["range"], "skill range", 0, 10)
            integer(skill["move_allowance"], "move allowance", 0, 10)
            integer(skill["uses_per_round"], "lab uses_per_round", 1, 3)
            if type(skill["preserve_effects"]) is not bool:
                raise EngineError("preserve_effects must be boolean")
            if skill["kind"] != "self_refresh" and skill["move_allowance"] != 0:
                raise EngineError("only self_refresh grants an immediate movement allowance")
            if skill["kind"] != "ally_refresh" and skill["range"] != 0:
                raise EngineError("self lab skills must have range 0")
            if skill["effect"] is not None:
                effect_definition(skill["effect"])
    if any(count < 1 or count > 5 for count in owners):
        raise EngineError("each laboratory side needs 1..5 units")
    return copy.deepcopy(config)


def mobility(hero_movement, soldier_movement):
    integer(hero_movement, "hero mobility", 0, 10)
    integer(soldier_movement, "soldier mobility", 0, 10)
    return min(hero_movement, soldier_movement)


def install_effect(unit, definition, round_number):
    counter = unit["completed_actions"] + 1 if definition["clock"] == "owner_action_end" else round_number
    timer = {"id": definition["id"], "clock": definition["clock"], "remaining": definition["remaining"],
             "next_tick": counter + int(definition["first_tick"] == "following_boundary")}
    # Explicit lab policy: same-id reapplication replaces its timer, no stacking.
    unit["effects"] = [e for e in unit["effects"] if e["id"] != timer["id"]] + [timer]


def initial_state(config):
    units = []
    for spec in config["units"]:
        unit = copy.deepcopy(spec)
        unit.update(max_hp=spec["hp"], movement=mobility(spec["hero_movement"], spec["soldier_movement"]),
                    acted=0, completed_actions=0, effects=[],
                    cooldowns={s["id"]: {"remaining": 0, "next_tick": 1} for s in spec["skills"]},
                    uses={s["id"]: 0 for s in spec["skills"]})
        for effect in spec["effects"]:
            install_effect(unit, effect, 1)
        units.append(unit)
    return {"phase": "battle", "battle": {"round": 1, "active_player": config["first_player"],
            "outcome": -2, "units": units},
            "lifecycle": {"activation_serial": 0, "action_serial": 0, "active_unit": None, "pending": None}}


def native_view(state):
    result = copy.deepcopy(state)
    pending = state["lifecycle"]["pending"]
    if pending:
        for unit in result["battle"]["units"]:
            if unit["id"] == pending["unit"]:
                unit["movement"] = pending["move_allowance"]
    return result


def legal_actions(config, state):
    from .game import native
    if state["phase"] == "finished":
        return []
    pending = state["lifecycle"]["pending"]
    units = {u["id"]: u for u in state["battle"]["units"]}
    raw = native(config, native_view(state), "legal")
    result = []
    for action in raw:
        if pending and action["unit"] != pending["unit"]:
            continue
        if pending and pending["kind"] == "post_move":
            if action["kind"] == "wait":
                result.append({**action, "kind": "finish_move"})
            continue
        result.append(action)
        if action["kind"] != "wait":
            continue
        unit = units[action["unit"]]
        for skill in unit["skills"]:
            if (unit["cooldowns"][skill["id"]]["remaining"]
                    or unit["uses"][skill["id"]] >= skill["uses_per_round"]):
                continue
            targets = [unit]
            if skill["kind"] == "ally_refresh":
                targets = [u for u in units.values() if u["owner"] == unit["owner"]
                           and u["hp"] > 0 and u["acted"] and u["id"] != unit["id"]
                           and abs(action["to"][0] - u["x"]) + abs(action["to"][1] - u["y"]) <= skill["range"]]
            for target in targets:
                result.append({**action, "kind": "skill", "skill": skill["id"], "target": target["id"]})
    return [{"action_id": digest(a), **a} for a in result]


def tick_effects(unit, clock, counter, events, preserve=False):
    keep = []
    for effect in unit["effects"]:
        if effect["clock"] == clock and effect["next_tick"] <= counter:
            if preserve:
                events.append({"type": "effect_tick_preserved", "unit": unit["id"], "effect": effect["id"]})
            else:
                effect["remaining"] -= 1
                effect["next_tick"] = counter + 1
                events.append({"type": "effect_tick", "unit": unit["id"], "effect": effect["id"],
                               "clock": clock, "remaining": effect["remaining"]})
        if effect["remaining"]:
            keep.append(effect)
        else:
            events.append({"type": "effect_expired", "unit": unit["id"], "effect": effect["id"]})
    unit["effects"] = keep


def handoff(config, state, actor, events):
    battle, lifecycle = state["battle"], state["lifecycle"]
    lifecycle["active_unit"] = None
    events.append({"type": "activation_end", "unit": actor["id"], "activation": lifecycle["activation_serial"]})
    living = [u for u in battle["units"] if u["hp"] > 0]
    owners = {u["owner"] for u in living}
    if len(owners) == 1:
        battle["outcome"] = next(iter(owners))
    elif not any(not u["acted"] for u in living):
        events.append({"type": "round_end", "round": battle["round"]})
        for unit in living:
            tick_effects(unit, "round_end", battle["round"], events)
        if battle["round"] == config["round_limit"]:
            battle["outcome"] = -1  # Lab completion rule, NOT Apex tiebreak logic.
        else:
            battle["round"] += 1
            battle["active_player"] = config["first_player"]
            for unit in living:
                unit["acted"] = 0
                unit["uses"] = {key: 0 for key in unit["uses"]}
            events.append({"type": "round_start", "round": battle["round"]})
    else:
        other = 1 - actor["owner"]
        battle["active_player"] = other if any(u["owner"] == other and not u["acted"] for u in living) else actor["owner"]
    if battle["outcome"] != -2:
        state["phase"] = "finished"
        events.append({"type": "match_finished", "outcome": battle["outcome"]})


def finish_action(config, state, actor, events, preserve=False, retain=False):
    actor["completed_actions"] += 1
    events.append({"type": "action_end", "unit": actor["id"], "action": state["lifecycle"]["action_serial"]})
    tick_effects(actor, "owner_action_end", actor["completed_actions"], events, preserve)
    for skill_id, cooldown in actor["cooldowns"].items():
        if cooldown["remaining"] and cooldown["next_tick"] <= actor["completed_actions"]:
            cooldown["remaining"] -= 1
            cooldown["next_tick"] = actor["completed_actions"] + 1
            events.append({"type": "cooldown_tick", "unit": actor["id"], "skill": skill_id,
                           "remaining": cooldown["remaining"]})
    actor["acted"] = 0 if retain else 1
    if not retain:
        handoff(config, state, actor, events)


def apply_action(config, state, action_id):
    from .game import native
    action = next((a for a in legal_actions(config, state) if a["action_id"] == action_id), None)
    if action is None:
        raise EngineError("action_id is not legal in this lifecycle state")
    updated = copy.deepcopy(state)
    battle, lifecycle = updated["battle"], updated["lifecycle"]
    actor = next(u for u in battle["units"] if u["id"] == action["unit"])
    pending = lifecycle["pending"]
    events = []
    if not pending:
        lifecycle["activation_serial"] += 1
        lifecycle["active_unit"] = actor["id"]
        events.append({"type": "activation_start", "unit": actor["id"], "activation": lifecycle["activation_serial"]})
    if not pending or pending["kind"] != "post_move":
        lifecycle["action_serial"] += 1
        events.append({"type": "action_start", "unit": actor["id"], "action": lifecycle["action_serial"]})
    movement = {**action, "target": action["target"] if action["kind"] == "attack" else -1}
    resolved = native(config, native_view(state), "resolve", movement)
    for native_unit in resolved["state"]["units"]:
        unit = next(u for u in battle["units"] if u["id"] == native_unit["id"])
        for key in ("x", "y", "hp"):
            unit[key] = native_unit[key]
    events.extend(resolved["events"])
    lifecycle["pending"] = None
    if pending and pending["kind"] == "post_move":
        events.append({"type": "post_move_end", "unit": actor["id"]})
        finish_action(config, updated, actor, events)
        return updated, events
    if action["kind"] == "skill":
        skill = next(s for s in actor["skills"] if s["id"] == action["skill"])
        actor["uses"][skill["id"]] += 1
        actor["cooldowns"][skill["id"]] = {"remaining": skill["cooldown"],
                                            "next_tick": actor["completed_actions"] + 2}
        target = next(u for u in battle["units"] if u["id"] == action["target"])
        events.append({"type": "skill_cast", "unit": actor["id"], "skill": skill["id"], "target": target["id"]})
        if skill["effect"] is not None:
            install_effect(target, skill["effect"], battle["round"])
            events.append({"type": "effect_applied", "unit": target["id"], "effect": skill["effect"]["id"]})
        if skill["kind"] == "ally_refresh":
            target["acted"] = 0
            events.append({"type": "ally_reactivated", "unit": target["id"]})
        if skill["kind"] == "self_refresh":
            lifecycle["pending"] = {"kind": "act_again", "unit": actor["id"],
                                    "move_allowance": skill["move_allowance"]}
            events.append({"type": "act_again_granted", "unit": actor["id"], "movement": skill["move_allowance"]})
        finish_action(config, updated, actor, events, skill["preserve_effects"], skill["kind"] == "self_refresh")
    elif (action["kind"] == "attack" and actor["post_attack_move"]
          and any(u["owner"] != actor["owner"] and u["hp"] > 0 for u in battle["units"])):
        lifecycle["pending"] = {"kind": "post_move", "unit": actor["id"], "move_allowance": actor["post_attack_move"]}
        events.append({"type": "post_move_start", "unit": actor["id"], "movement": actor["post_attack_move"]})
    else:
        finish_action(config, updated, actor, events)
    return updated, events


def decision_bound(config):
    extra = sum(s["uses_per_round"] for u in config["units"] for s in u["skills"]
                if s["kind"] in ("self_refresh", "ally_refresh"))
    return 2 * config["round_limit"] * (len(config["units"]) + extra)
