"""Baseline players for exercising the stand; neither is a learned policy."""
import random

from .game import RULESET, digest
from . import __version__


def submission(envelope, action_id):
    request = envelope["request"]
    return {"request_id": request["request_id"], "state_hash": request["state_hash"],
            "expected_version": envelope["version"], "player": request["player"],
            "action_id": action_id}


def choose_action(request, kind, rng):
    actions = request["legal_actions"]
    if not actions:
        raise ValueError("no legal actions in decision request")
    if kind == "random":
        return rng.choice(actions)
    if kind != "heuristic":
        raise ValueError("unknown baseline agent")
    obs = request["observation"]
    state = obs["state"]
    if state["phase"] == "draft":
        owner = 1 - request["player"] if actions[0]["kind"] == "ban" else request["player"]
        heroes = {h["id"]: h for h in obs["boxes"][owner]}
        return max(actions, key=lambda a: (heroes[a["hero"]]["attack"]
                   + heroes[a["hero"]]["hp"] + heroes[a["hero"]]["range"] * 3,
                   a["action_id"]))
    units = {u["id"]: u for u in state["battle"]["units"]}

    def score(action):
        unit = units[action["unit"]]
        enemies = [u for u in units.values() if u["owner"] != unit["owner"] and u["hp"] > 0]
        x, y = action["to"]
        distance = min(abs(x - e["x"]) + abs(y - e["y"]) for e in enemies)
        damage, kill = 0, 0
        if action["target"] >= 0:
            target = units[action["target"]]
            damage = min(target["hp"], max(1, unit["attack"] - target["defense"]))
            kill = int(damage == target["hp"])
        return (kill, damage, -distance, action["action_id"])

    return max(actions, key=score)


def run_selfplay(stand, config, episodes, seed, players, output):
    """Collect reproducible baseline trajectories, not neural-network training."""
    import json
    from pathlib import Path
    import time

    from .game import current_player, integer, schedule
    from .stand import verify_replay

    integer(episodes, "episodes", 1, 10000)
    integer(seed, "seed", 0, 2**63 - 1)
    if len(players) != 2 or any(p not in ("random", "heuristic") for p in players):
        raise ValueError("two baseline players required")
    output = Path(output)
    # Never silently overwrite results from an earlier experiment.
    output.mkdir(parents=True, exist_ok=False)
    rng = random.Random(seed)
    outcomes = {"0": 0, "1": 0, "draw": 0}
    started = time.monotonic()
    total_decisions = 0
    with (output / "trajectories.jsonl").open("w") as dataset:
        for episode in range(episodes):
            match_id = stand.create_match(config)["match_id"]
            trajectory = []
            bound = config["round_limit"] * config["draft"]["team_size"] * 2
            bound += len(schedule(config))
            for _ in range(bound + 1):
                replay = stand.get_replay(match_id)
                player = current_player(config, replay["final_state"])
                if player is None:
                    break
                envelope = stand.get_decision_request(match_id, player)
                action = choose_action(envelope["request"], players[player], rng)
                trajectory.append({"episode": episode, "match_id": match_id,
                                   "version": envelope["version"], "player": player,
                                   "agent": players[player], "request": envelope["request"],
                                   "action_id": action["action_id"]})
                stand.submit_action(match_id, submission(envelope, action["action_id"]))
            replay = stand.get_replay(match_id)
            if not verify_replay(replay)["finished"]:
                raise ValueError("fixture exceeded its finite decision bound")
            winner = replay["final_state"]["battle"]["outcome"]
            outcomes[str(winner) if winner >= 0 else "draw"] += 1
            for row in trajectory:
                row["terminal_value"] = 0 if winner < 0 else (1 if row["player"] == winner else -1)
                dataset.write(json.dumps(row, sort_keys=True) + "\n")
            dataset.flush()
            total_decisions += len(trajectory)
            (output / f"episode-{episode:05d}.json").write_text(
                json.dumps(replay, indent=2) + "\n")
    report = {"ruleset": RULESET, "engine_version": __version__,
              "fidelity": "synthetic_fixture", "training": False,
              "players": players, "episodes": episodes, "seed": seed,
              "config_hash": digest(config), "outcomes": outcomes,
              "decisions": total_decisions, "elapsed_seconds": time.monotonic() - started,
              "output": str(output)}
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
