"""Versioned synthetic fixture, draft state machine and native-core boundary.

No real hero or Langrisser formula is implemented. Unknown rulesets fail closed.
"""
import copy
import json
import os
from pathlib import Path
import subprocess

from .errors import EngineError
from .schema import canonical, digest, integer, keys, validate_fixture_hero

RULESET = "protocol-fixture-v0"
ROOT = Path(__file__).resolve().parents[1]


def validate_config(config):
    if isinstance(config, dict) and config.get("ruleset") in ("action-lifecycle-lab-v1", "terrain-lab-v1"):
        from .lifecycle import validate_config as validate_lifecycle
        return validate_lifecycle(config)
    fields = ["ruleset", "map", "round_limit", "draft", "boxes"]
    if isinstance(config, dict) and "content_snapshot" in config:
        fields.append("content_snapshot")
    keys(config, fields, "scenario")
    if config["ruleset"] != RULESET:
        raise EngineError("unsupported ruleset: expected a supported fixture or laboratory ruleset")
    board = config["map"]
    keys(board, ["width", "height", "costs"], "map")
    width = integer(board["width"], "width", 2, 32)
    height = integer(board["height"], "height", 2, 32)
    if not isinstance(board["costs"], list) or len(board["costs"]) != width * height:
        raise EngineError("costs must contain width * height entries in row-major order")
    for cost in board["costs"]:
        integer(cost, "terrain cost", 0, 9)
    integer(config["round_limit"], "round_limit", 1, 100)
    draft = config["draft"]
    keys(draft, ["enabled", "team_size", "bans_per_side"], "draft")
    if type(draft["enabled"]) is not bool:
        raise EngineError("draft.enabled must be a boolean")
    team_size = integer(draft["team_size"], "team_size", 1, 5)
    bans = integer(draft["bans_per_side"], "bans_per_side", 0, 10)
    if not draft["enabled"] and bans:
        raise EngineError("fixed teams require bans_per_side=0")
    if height < team_size:
        raise EngineError("map height must accommodate team_size")
    boxes = config["boxes"]
    if not isinstance(boxes, list) or len(boxes) != 2:
        raise EngineError("boxes must contain exactly two hero lists")
    for side, box in enumerate(boxes):
        if not isinstance(box, list) or not team_size + bans <= len(box) <= 20:
            raise EngineError("each box needs enough heroes for picks and bans (at most 20)")
        if not draft["enabled"] and len(box) != team_size:
            raise EngineError("fixed boxes must contain exactly team_size heroes")
        ids = set()
        for hero in box:
            hero_id = validate_fixture_hero(hero)
            if hero_id in ids:
                raise EngineError(f"duplicate hero id in box {side}")
            ids.add(hero_id)
    for side in (0, 1):
        for i in range(team_size):
            x, y = spawn(board, team_size, side, i)
            if board["costs"][y * width + x] == 0:
                raise EngineError("deployment tiles must be passable")
    if "content_snapshot" in config:
        from .content import validate_runtime_binding
        validate_runtime_binding(config["content_snapshot"], config)
    return copy.deepcopy(config)


def spawn(board, team_size, side, index):
    return (0 if side == 0 else board["width"] - 1,
            (index + 1) * board["height"] // (team_size + 1))


def schedule(config):
    draft = config["draft"]
    return ([{"kind": "ban", "player": p} for _ in range(draft["bans_per_side"])
             for p in (0, 1)] +
            [{"kind": "pick", "player": p} for _ in range(draft["team_size"])
             for p in (0, 1)])


def initial_state(config):
    config = validate_config(config)
    if config["ruleset"] in ("action-lifecycle-lab-v1", "terrain-lab-v1"):
        from .lifecycle import initial_state as initial_lifecycle
        return initial_lifecycle(config)
    state = {"phase": "draft", "draft_index": 0, "picked": [[], []],
             "banned": [[], []], "battle": None}
    if not config["draft"]["enabled"]:
        state["picked"] = [[hero["id"] for hero in box] for box in config["boxes"]]
        deploy(config, state)
    return state


def deploy(config, state):
    units = []
    size = config["draft"]["team_size"]
    for side in (0, 1):
        heroes = {h["id"]: h for h in config["boxes"][side]}
        for i, hero_id in enumerate(state["picked"][side]):
            hero = heroes[hero_id]
            x, y = spawn(config["map"], size, side, i)
            units.append({"id": side * size + i, "owner": side, "x": x, "y": y,
                          "hp": hero["hp"], "max_hp": hero["hp"],
                          **{key: hero[key] for key in ("attack", "defense", "movement", "range")},
                          "acted": 0})
    state["battle"] = {"round": 1, "active_player": 0, "outcome": -2, "units": units}
    state["phase"] = "battle"


def current_player(config, state):
    if state["phase"] == "finished":
        return None
    if state["phase"] == "draft":
        return schedule(config)[state["draft_index"]]["player"]
    return state["battle"]["active_player"]


def state_hash(config, state):
    return digest({"protocol": 1, "config": config, "state": state})


def native(config, state, command, action=None):
    binary = Path(os.environ.get("APEX_NATIVE_BIN", ROOT / "build" / "apex_fixture"))
    if not binary.is_file():
        raise EngineError("native fixture missing; run: python scripts/build_native.py")
    board, battle = config["map"], state["battle"]
    values = [board["width"], board["height"], config["round_limit"], battle["round"],
              battle["active_player"], battle["outcome"], *board["costs"], len(battle["units"])]
    for unit in battle["units"]:
        values += [unit[key] for key in ("id", "owner", "x", "y", "hp", "max_hp",
                                         "attack", "defense", "movement", "range", "acted")]
    if action is not None:
        values += [action["unit"], *action["to"], action["target"]]
    try:
        result = subprocess.run([str(binary), command], input=" ".join(map(str, values)),
                                text=True, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise EngineError(f"native fixture unavailable: {error}") from error
    if result.returncode:
        raise EngineError(f"native fixture rejected state/action: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise EngineError("invalid response from native fixture") from error


def legal_actions(config, state):
    if config["ruleset"] in ("action-lifecycle-lab-v1", "terrain-lab-v1"):
        from .lifecycle import legal_actions as lifecycle_actions
        return lifecycle_actions(config, state)
    if state["phase"] == "finished":
        return []
    if state["phase"] == "draft":
        step = schedule(config)[state["draft_index"]]
        side = 1 - step["player"] if step["kind"] == "ban" else step["player"]
        excluded = state["picked"][side] + state["banned"][side]
        actions = [{"kind": step["kind"], "hero": hero["id"]}
                   for hero in config["boxes"][side] if hero["id"] not in excluded]
    else:
        actions = native(config, state, "legal")
    return [{"action_id": digest(action), **action} for action in actions]


def apply_action(config, state, action_id):
    if config["ruleset"] in ("action-lifecycle-lab-v1", "terrain-lab-v1"):
        from .lifecycle import apply_action as lifecycle_apply
        return lifecycle_apply(config, state, action_id)
    action = next((a for a in legal_actions(config, state) if a["action_id"] == action_id), None)
    if action is None:
        raise EngineError("action_id is not legal in this state")
    updated = copy.deepcopy(state)
    if state["phase"] == "draft":
        step = schedule(config)[state["draft_index"]]
        side = 1 - step["player"] if step["kind"] == "ban" else step["player"]
        updated["banned" if step["kind"] == "ban" else "picked"][side].append(action["hero"])
        updated["draft_index"] += 1
        events = [{"type": step["kind"], "player": step["player"],
                   "box_owner": side, "hero": action["hero"]}]
        if updated["draft_index"] == len(schedule(config)):
            deploy(config, updated)
            events.append({"type": "fixture_deployment"})
    else:
        result = native(config, state, "apply", action)
        updated["battle"] = result["state"]
        events = result["events"]
        if result["state"]["outcome"] != -2:
            updated["phase"] = "finished"
    return updated, events


def observation(config, state, player):
    """Fixture is perfect-information. Do not reuse this for hidden-info rulesets."""
    integer(player, "player", 0, 1)
    if config["ruleset"] in ("action-lifecycle-lab-v1", "terrain-lab-v1"):
        return {"ruleset": config["ruleset"], "fidelity": fidelity(config), "player": player,
                "map": copy.deepcopy(config["map"]), "round_limit": config["round_limit"],
                "state": copy.deepcopy(state)}
    result = {"ruleset": RULESET, "fidelity": "synthetic_fixture", "player": player,
            "map": copy.deepcopy(config["map"]), "round_limit": config["round_limit"],
            "boxes": copy.deepcopy(config["boxes"]), "state": copy.deepcopy(state)}
    if "content_snapshot" in config:
        from .content import experiment_metadata
        result["experiment"] = experiment_metadata(config["content_snapshot"])
    return result


def fidelity(config):
    return "mechanics_lab" if config["ruleset"] in ("action-lifecycle-lab-v1", "terrain-lab-v1") else "synthetic_fixture"


def supported_rulesets():
    return {RULESET: "synthetic_fixture", "action-lifecycle-lab-v1": "mechanics_lab", "terrain-lab-v1": "mechanics_lab"}


def decision_bound(config):
    if config["ruleset"] in ("action-lifecycle-lab-v1", "terrain-lab-v1"):
        from .lifecycle import decision_bound as lifecycle_bound
        return lifecycle_bound(config)
    return config["round_limit"] * config["draft"]["team_size"] * 2 + len(schedule(config))
