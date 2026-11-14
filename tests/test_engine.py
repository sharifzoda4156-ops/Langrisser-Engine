import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from apex_engine.agents import run_selfplay, submission
from apex_engine.errors import Conflict, EngineError
from apex_engine.game import (ROOT, apply_action, initial_state, legal_actions, native,
                              validate_config)
from apex_engine.http_server import make_server
from apex_engine.stand import Stand, verify_replay


def scenario(fixed=False):
    config = json.loads((ROOT / "scenarios" / "protocol_fixture.json").read_text())
    if fixed:
        config["draft"] = {"enabled": False, "team_size": 1, "bans_per_side": 0}
        config["boxes"] = [[box[0]] for box in config["boxes"]]
    return config


class EngineTests(unittest.TestCase):
    def test_weighted_movement_and_walls(self):
        config = scenario(True)
        config["map"] = {"width": 5, "height": 3,
                         "costs": [0, 0, 0, 0, 0, 1, 2, 1, 1, 1, 0, 0, 0, 0, 0]}
        state = initial_state(config)
        actions = legal_actions(config, state)
        endpoints = {tuple(a["to"]) for a in actions}
        self.assertEqual(endpoints, {(0, 1), (1, 1)})
        moved = next(a for a in actions if a["to"] == [1, 1])
        self.assertEqual(moved["path"], [[0, 1], [1, 1]])

    def test_occupied_tiles_block_routes(self):
        config = scenario(True)
        config["map"] = {"width": 5, "height": 2, "costs": [0] * 5 + [1] * 5}
        state = initial_state(config)
        state["battle"]["units"][1]["x"] = 1
        state["battle"]["units"][0]["movement"] = 4
        actions = legal_actions(config, state)
        self.assertEqual({tuple(a["to"]) for a in actions}, {(0, 1)})
        self.assertTrue(any(a["kind"] == "attack" for a in actions))

    def test_native_rejects_illegal_action(self):
        config = scenario(True)
        state = initial_state(config)
        with self.assertRaises(EngineError):
            native(config, state, "apply", {"unit": 0, "to": [99, 99], "target": -1})

    def test_kill_and_terminal_state(self):
        config = scenario(True)
        config["map"] = {"width": 2, "height": 2, "costs": [1] * 4}
        config["boxes"][0][0]["attack"] = 100
        state = initial_state(config)
        attack = next(a for a in legal_actions(config, state) if a["kind"] == "attack")
        updated, events = apply_action(config, state, attack["action_id"])
        self.assertEqual(updated["phase"], "finished")
        self.assertEqual(updated["battle"]["outcome"], 0)
        self.assertEqual(legal_actions(config, updated), [])
        self.assertEqual(events[-1], {"type": "match_finished", "outcome": 0})
        self.assertEqual(state["battle"]["units"][1]["hp"], 14)

    def test_round_limit_draw_and_player_alternation(self):
        config = scenario(True)
        config["round_limit"] = 1
        state = initial_state(config)
        for player in (0, 1):
            self.assertEqual(state["battle"]["active_player"], player)
            action = next(a for a in legal_actions(config, state)
                          if a["kind"] == "wait" and a["to"] ==
                          [state["battle"]["units"][player]["x"],
                           state["battle"]["units"][player]["y"]])
            state, _ = apply_action(config, state, action["action_id"])
        self.assertEqual(state["battle"]["outcome"], -1)

    def test_new_round_resets_activations(self):
        config = scenario(True)
        state = initial_state(config)
        for _ in range(2):
            state, _ = apply_action(config, state, legal_actions(config, state)[0]["action_id"])
        self.assertEqual(state["battle"]["round"], 2)
        self.assertEqual(state["battle"]["active_player"], 0)
        self.assertTrue(all(not u["acted"] for u in state["battle"]["units"]))

    def test_invalid_configs_fail_closed(self):
        for mutate in (lambda c: c.update(ruleset="global-apex"),
                       lambda c: c["draft"].update(team_size=True),
                       lambda c: c["boxes"][0][0].update(id="leon_sp"),
                       lambda c: c["boxes"][0][0].update(guard=True),
                       lambda c: c["boxes"][0][0].update(hp=float("nan")),
                       lambda c: c["map"].update(costs=[]),
                       lambda c: c["draft"].update(bans_per_side=9)):
            config = scenario()
            mutate(config)
            with self.subTest(config=config):
                with self.assertRaises(EngineError):
                    validate_config(config)


class StandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "stand.sqlite3"
        self.stand = Stand(self.database)
        self.match_id = self.stand.create_match(scenario())["match_id"]

    def tearDown(self):
        self.temp.cleanup()

    def envelope(self, player=0):
        return self.stand.get_decision_request(self.match_id, player)

    def test_draft_to_battle_and_bans(self):
        expected = [(0, "ban"), (1, "ban"), (0, "pick"), (1, "pick"), (0, "pick"), (1, "pick")]
        banned = {}
        for player, kind in expected:
            envelope = self.envelope(player)
            actions = envelope["request"]["legal_actions"]
            self.assertTrue(all(a["kind"] == kind for a in actions))
            if kind == "pick":
                self.assertNotIn(banned[player], [a["hero"] for a in actions])
            else:
                banned[1 - player] = actions[0]["hero"]
            self.stand.submit_action(self.match_id, submission(envelope, actions[0]["action_id"]))
        replay = self.stand.get_replay(self.match_id)
        self.assertEqual(replay["final_state"]["phase"], "battle")
        self.assertEqual(len(replay["final_state"]["battle"]["units"]), 4)
        self.assertTrue(verify_replay(replay)["verified"])

    def test_waiting_player_receives_no_request(self):
        response = self.envelope(1)
        self.assertIsNone(response["request"])
        self.assertTrue(response["waiting"])

    def test_restart_and_duplicate_submission(self):
        envelope = self.envelope()
        payload = submission(envelope, envelope["request"]["legal_actions"][0]["action_id"])
        first = self.stand.submit_action(self.match_id, payload)
        restarted = Stand(self.database)
        self.assertEqual(first, restarted.submit_action(self.match_id, payload))
        replay = restarted.get_replay(self.match_id)
        self.assertEqual(replay["version"], 1)
        self.assertEqual(len(replay["decisions"]), 1)

    def test_conflicting_retry_and_stale_state_are_rejected(self):
        envelope = self.envelope()
        actions = envelope["request"]["legal_actions"]
        payload = submission(envelope, actions[0]["action_id"])
        self.stand.submit_action(self.match_id, payload)
        with self.assertRaises(Conflict):
            self.stand.submit_action(self.match_id, {**payload, "action_id": actions[1]["action_id"]})
        with self.assertRaises(Conflict):
            self.stand.submit_action(self.match_id, {**payload, "request_id": "0" * 64})
        self.assertEqual(self.stand.get_replay(self.match_id)["version"], 1)

    def test_invalid_action_or_hash_does_not_mutate(self):
        envelope = self.envelope()
        before = self.stand.get_replay(self.match_id)
        payload = submission(envelope, "0" * 64)
        with self.assertRaises(EngineError):
            self.stand.submit_action(self.match_id, payload)
        with self.assertRaises(Conflict):
            self.stand.submit_action(self.match_id, {**payload, "state_hash": "0" * 64})
        self.assertEqual(before, self.stand.get_replay(self.match_id))

    def test_concurrent_identical_submissions_execute_once(self):
        envelope = self.envelope()
        payload = submission(envelope, envelope["request"]["legal_actions"][0]["action_id"])
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(lambda _: self.stand.submit_action(self.match_id, payload), range(4)))
        self.assertTrue(all(r == receipts[0] for r in receipts))
        self.assertEqual(self.stand.get_replay(self.match_id)["version"], 1)

    def test_concurrent_different_submissions_have_one_winner(self):
        envelope = self.envelope()
        actions = envelope["request"]["legal_actions"]

        def send(action):
            try:
                self.stand.submit_action(self.match_id, submission(envelope, action["action_id"]))
                return "accepted"
            except Conflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(send, actions[:2]))
        self.assertCountEqual(outcomes, ["accepted", "conflict"])
        replay = self.stand.get_replay(self.match_id)
        self.assertEqual(replay["version"], 1)
        self.assertTrue(verify_replay(replay)["verified"])

    def test_boolean_actor_is_not_an_integer_in_replay(self):
        for player in (0, 1):
            envelope = self.envelope(player)
            self.stand.submit_action(self.match_id, submission(
                envelope, envelope["request"]["legal_actions"][0]["action_id"]))
        replay = self.stand.get_replay(self.match_id)
        replay["decisions"][1]["submission"]["player"] = True
        with self.assertRaises(EngineError):
            verify_replay(replay)

    def test_malformed_replay_is_rejected(self):
        for replay in ({}, {"protocol_version": 1}, [], None):
            with self.subTest(replay=replay):
                with self.assertRaises(EngineError):
                    verify_replay(replay)

    def test_replay_detects_changed_events_and_state(self):
        envelope = self.envelope()
        self.stand.submit_action(self.match_id,
                                 submission(envelope, envelope["request"]["legal_actions"][0]["action_id"]))
        replay = self.stand.get_replay(self.match_id)
        self.assertTrue(verify_replay(replay)["verified"])
        for mutate in (lambda r: r["decisions"][0]["receipt"]["events"].clear(),
                       lambda r: r["final_state"].update(draft_index=99),
                       lambda r: r.update(final_hash="0" * 64),
                       lambda r: r["decisions"][0]["submission"].update(player=True)):
            changed = copy.deepcopy(replay)
            mutate(changed)
            with self.assertRaises(EngineError):
                verify_replay(changed)

    def test_baseline_selfplay_finishes_and_exports_terminal_rewards(self):
        output = Path(self.temp.name) / "experiment"
        report = run_selfplay(self.stand, scenario(), 2, 12, ["heuristic", "random"], output)
        self.assertFalse(report["training"])
        self.assertEqual(sum(report["outcomes"].values()), 2)
        rows = [json.loads(line) for line in (output / "trajectories.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), report["decisions"])
        self.assertTrue(all(row["terminal_value"] in (-1, 0, 1) for row in rows))
        for path in output.glob("episode-*.json"):
            self.assertTrue(verify_replay(json.loads(path.read_text()))["finished"])
        with self.assertRaises(FileExistsError):
            run_selfplay(self.stand, scenario(), 1, 12, ["random", "random"], output)

    def test_seed_reproduces_games(self):
        results = []
        for number in range(2):
            output = Path(self.temp.name) / f"run{number}"
            run_selfplay(self.stand, scenario(), 1, 99, ["random", "random"], output)
            replay = json.loads((output / "episode-00000.json").read_text())
            results.append((replay["final_hash"], [d["submission"]["action_id"] for d in replay["decisions"]]))
        self.assertEqual(results[0], results[1])


class HTTPTests(unittest.TestCase):
    def test_external_player_round_trip_and_origin_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            server = make_server(Path(temp) / "stand.sqlite3", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"

            def call(path, data=None, origin=None):
                headers = {"Content-Type": "application/json"}
                if origin:
                    headers["Origin"] = origin
                request = Request(base + path, data=None if data is None else json.dumps(data).encode(),
                                  headers=headers)
                with urlopen(request, timeout=5) as response:
                    return json.load(response)

            try:
                self.assertEqual(call("/health")["status"], "ok")
                match_id = call("/matches", scenario())["match_id"]
                envelope = call(f"/matches/{match_id}/request?player=0")
                payload = submission(envelope, envelope["request"]["legal_actions"][0]["action_id"])
                receipt = call(f"/matches/{match_id}/actions", payload)
                self.assertEqual(receipt, call(f"/matches/{match_id}/actions", payload))
                self.assertTrue(verify_replay(call(f"/matches/{match_id}/replay"))["verified"])
                with self.assertRaises(HTTPError) as blocked:
                    call("/matches", scenario(), "https://unrelated.example")
                self.assertEqual(blocked.exception.code, 403)
                with self.assertRaises(HTTPError) as conflict:
                    call(f"/matches/{match_id}/actions", {**payload, "request_id": "0" * 64})
                self.assertEqual(conflict.exception.code, 409)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
