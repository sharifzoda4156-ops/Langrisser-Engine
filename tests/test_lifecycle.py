import copy
import json
from pathlib import Path
import tempfile
import unittest

from apex_engine.agents import run_selfplay, submission
from apex_engine.errors import EngineError
from apex_engine.game import (ROOT, apply_action, current_player, decision_bound,
                              initial_state, legal_actions, native, validate_config)
from apex_engine.lifecycle import mobility
from apex_engine.stand import Stand, verify_replay


def scenario():
    return json.loads((ROOT / "scenarios" / "action_lifecycle_lab.json").read_text())


def unit(state, unit_id=0):
    return next(u for u in state["battle"]["units"] if u["id"] == unit_id)


def choose(config, state, kind, actor=0, to=None, skill=None, target=None):
    actions = legal_actions(config, state)
    selected = next((a for a in actions if a["kind"] == kind and a["unit"] == actor
                     and (to is None or a["to"] == to) and (skill is None or a.get("skill") == skill)
                     and (target is None or a["target"] == target)), None)
    if selected is None:
        raise AssertionError(f"missing {kind} action for {actor} at {to}; available={actions}")
    return selected


def step(config, state, kind, actor=0, **kwargs):
    action = choose(config, state, kind, actor, **kwargs)
    return apply_action(config, state, action["action_id"])


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.config = scenario()
        self.state = initial_state(self.config)

    def test_documented_mobility_example(self):
        self.assertEqual(mobility(5, 3), 3)
        self.assertEqual(mobility(5, 5), 5)
        self.assertEqual(unit(self.state)["movement"], 3)
        self.assertFalse(any(a["to"] == [4, 0] for a in legal_actions(self.config, self.state)
                             if a["unit"] == 0))
        with self.assertRaises(EngineError):
            mobility(True, 3)

    def test_self_refresh_holds_actor_and_allows_another_full_action(self):
        original = copy.deepcopy(self.state)
        state, events = step(self.config, self.state, "skill", to=[0, 1], skill="fixture_self_refresh")
        self.assertEqual(self.state, original)
        self.assertEqual(current_player(self.config, state), 0)
        self.assertEqual(state["lifecycle"]["pending"]["kind"], "act_again")
        self.assertEqual(unit(state)["acted"], 0)
        self.assertEqual(unit(state)["completed_actions"], 1)
        self.assertTrue(all(a["unit"] == 0 for a in legal_actions(self.config, state)))
        self.assertTrue(any(a["kind"] == "attack" for a in legal_actions(self.config, state)))
        state, later = step(self.config, state, "wait", to=[0, 1])
        self.assertEqual(current_player(self.config, state), 1)
        self.assertEqual(state["lifecycle"]["activation_serial"], 1)
        self.assertEqual(state["lifecycle"]["action_serial"], 2)
        self.assertEqual(unit(state)["completed_actions"], 2)
        self.assertFalse(any(e["type"] == "activation_end" for e in events))
        self.assertTrue(any(e["type"] == "activation_end" for e in later))

    def test_post_attack_move_is_a_separate_restricted_decision(self):
        state, events = step(self.config, self.state, "attack", to=[3, 1], target=2)
        self.assertEqual(current_player(self.config, state), 0)
        self.assertEqual(state["lifecycle"]["pending"]["kind"], "post_move")
        self.assertEqual(unit(state)["completed_actions"], 0)
        self.assertFalse(any(e["type"] == "action_end" for e in events))
        allowed = legal_actions(self.config, state)
        self.assertEqual({a["kind"] for a in allowed}, {"finish_move"})
        self.assertEqual({a["unit"] for a in allowed}, {0})
        state, later = step(self.config, state, "finish_move", to=[0, 1])
        self.assertIsNone(state["lifecycle"]["pending"])
        self.assertEqual(current_player(self.config, state), 1)
        self.assertEqual(unit(state)["completed_actions"], 1)
        self.assertEqual(state["lifecycle"]["action_serial"], 1)
        self.assertEqual(sum(e["type"] == "action_end" for e in later), 1)

    def test_same_side_ready_units_cannot_interrupt_pending_continuation(self):
        old = choose(self.config, self.state, "wait", 1)["action_id"]
        state, _ = step(self.config, self.state, "attack", to=[3, 1], target=2)
        with self.assertRaises(EngineError):
            apply_action(self.config, state, old)

    def test_effect_preservation_is_explicit_per_skill(self):
        for preserve, remaining in [(True, 2), (False, 1)]:
            config = scenario()
            config["units"][0]["skills"][0]["preserve_effects"] = preserve
            state = initial_state(config)
            state, _ = step(config, state, "skill", to=[0, 1], skill="fixture_self_refresh")
            owner = next(e for e in unit(state)["effects"] if e["id"] == "fixture_owner_timer")
            self.assertEqual(owner["remaining"], remaining)

    def test_round_timers_do_not_tick_for_each_action(self):
        state, _ = step(self.config, self.state, "skill", to=[0, 1], skill="fixture_self_refresh")
        state, _ = step(self.config, state, "wait", to=[0, 1])
        self.assertEqual(next(e for e in unit(state)["effects"] if e["clock"] == "round_end")["remaining"], 2)
        for actor in (2, 1, 3):
            actor_unit = unit(state, actor)
            state, _ = step(self.config, state, "wait", actor, to=[actor_unit["x"], actor_unit["y"]])
        self.assertEqual(state["battle"]["round"], 2)
        self.assertEqual(next(e for e in unit(state)["effects"] if e["clock"] == "round_end")["remaining"], 1)

    def test_post_move_completion_ticks_owner_timers_once(self):
        state, _ = step(self.config, self.state, "attack", to=[3, 1], target=2)
        self.assertEqual(next(e for e in unit(state)["effects"] if e["clock"] == "owner_action_end")["remaining"], 2)
        state, _ = step(self.config, state, "finish_move", to=[3, 1])
        self.assertEqual(next(e for e in unit(state)["effects"] if e["clock"] == "owner_action_end")["remaining"], 1)

    def test_self_refresh_attack_and_post_move_share_one_activation(self):
        state, _ = step(self.config, self.state, "skill", to=[0, 1], skill="fixture_self_refresh")
        state, _ = step(self.config, state, "attack", to=[3, 1], target=2)
        self.assertEqual(unit(state)["completed_actions"], 1)
        state, events = step(self.config, state, "finish_move", to=[0, 1])
        self.assertEqual(unit(state)["completed_actions"], 2)
        self.assertEqual(state["lifecycle"]["action_serial"], 2)
        self.assertEqual(state["lifecycle"]["activation_serial"], 1)
        self.assertEqual(sum(e["type"] == "action_end" for e in events), 1)
        self.assertEqual(current_player(self.config, state), 1)

    def test_effect_expires_once_and_following_boundary_is_respected(self):
        config = scenario()
        config["units"][0]["effects"][0]["remaining"] = 1
        state = initial_state(config)
        state, events = step(config, state, "wait", to=[0, 1])
        self.assertFalse(any(e["id"] == "fixture_owner_timer" for e in unit(state)["effects"]))
        self.assertEqual(sum(e["type"] == "effect_expired" for e in events), 1)
        config["units"][0]["effects"][0]["first_tick"] = "following_boundary"
        state = initial_state(config)
        state, events = step(config, state, "wait", to=[0, 1])
        self.assertTrue(any(e["id"] == "fixture_owner_timer" for e in unit(state)["effects"]))
        self.assertFalse(any(e["type"] == "effect_expired" for e in events))

    def test_new_cooldown_skips_cast_boundary_then_ticks_on_next_action(self):
        state, _ = step(self.config, self.state, "skill", to=[0, 1], skill="fixture_self_refresh")
        self.assertEqual(unit(state)["cooldowns"]["fixture_self_refresh"]["remaining"], 2)
        self.assertFalse(any(a.get("skill") == "fixture_self_refresh" for a in legal_actions(self.config, state)))
        state, _ = step(self.config, state, "wait", to=[0, 1])
        self.assertEqual(unit(state)["cooldowns"]["fixture_self_refresh"]["remaining"], 1)

    def test_first_tick_policy_is_not_guessed(self):
        config = scenario()
        for first_tick, expected in [("current_boundary", 1), ("following_boundary", 2)]:
            timer = config["units"][1]["skills"][1]["effect"]
            timer["first_tick"] = first_tick
            state = initial_state(config)
            state, _ = step(config, state, "skill", 1, to=[0, 3], skill="fixture_timer_cast")
            self.assertEqual(unit(state, 1)["effects"][0]["remaining"], expected)

    def test_ally_reactivation_makes_target_ready_but_hands_over_normally(self):
        state, _ = step(self.config, self.state, "wait", to=[0, 1])
        state, _ = step(self.config, state, "wait", 2, to=[4, 1])
        self.assertEqual(unit(state)["acted"], 1)
        state, events = step(self.config, state, "skill", 1, to=[0, 3], skill="fixture_ally_refresh", target=0)
        self.assertEqual(unit(state)["acted"], 0)
        self.assertIsNone(state["lifecycle"]["pending"])
        self.assertEqual(current_player(self.config, state), 1)
        self.assertTrue(any(e["type"] == "ally_reactivated" for e in events))
        state, _ = step(self.config, state, "wait", 3, to=[4, 3])
        self.assertEqual(current_player(self.config, state), 0)
        self.assertEqual({a["unit"] for a in legal_actions(self.config, state)}, {0})

    def test_ally_refresh_cannot_target_self_or_unacted_ally(self):
        self.assertFalse(any(a.get("skill") == "fixture_ally_refresh" for a in legal_actions(self.config, self.state)))

    def test_last_unit_post_move_delays_round_boundary(self):
        config = scenario()
        config["first_player"] = 1
        state = initial_state(config)
        for actor in (2, 1, 3):
            u = unit(state, actor)
            state, _ = step(config, state, "wait", actor, to=[u["x"], u["y"]])
        state, events = step(config, state, "attack", to=[3, 1], target=2)
        self.assertEqual(state["battle"]["round"], 1)
        self.assertFalse(any(e["type"] == "round_end" for e in events))
        state, events = step(config, state, "finish_move", to=[3, 1])
        self.assertEqual(state["battle"]["round"], 2)
        self.assertTrue(any(e["type"] == "round_end" for e in events))

    def test_laboratory_first_player_is_explicit(self):
        config = scenario()
        config["first_player"] = 1
        state = initial_state(config)
        self.assertEqual(current_player(config, state), 1)
        for actor in (2, 0, 3, 1):
            u = unit(state, actor)
            state, _ = step(config, state, "wait", actor, to=[u["x"], u["y"]])
        self.assertEqual(state["battle"]["round"], 2)
        self.assertEqual(current_player(config, state), 1)

    def test_elimination_ends_before_post_move(self):
        config = scenario()
        config["units"] = [config["units"][0], config["units"][2]]
        config["units"][1]["hp"] = 1
        state = initial_state(config)
        state, _ = step(config, state, "attack", to=[3, 1], target=2)
        self.assertEqual(state["phase"], "finished")
        self.assertEqual(state["battle"]["outcome"], 0)
        self.assertIsNone(state["lifecycle"]["pending"])
        self.assertEqual(legal_actions(config, state), [])

    def test_native_resolve_does_not_advance_turn_or_mark_unit(self):
        action = choose(self.config, self.state, "wait", to=[0, 1])
        resolved = native(self.config, self.state, "resolve", action)
        self.assertEqual(resolved["state"]["round"], 1)
        self.assertEqual(resolved["state"]["active_player"], 0)
        self.assertEqual(resolved["state"]["units"][0]["acted"], 0)
        self.assertEqual([e["type"] for e in resolved["events"]], ["move"])

    def test_bad_or_unmodelled_mechanics_fail_explicitly(self):
        for mutate in (lambda c: c["units"][0].update(name="leon_sp"),
                       lambda c: c["units"][0].update(guard=True),
                       lambda c: c["units"][0]["skills"][0].update(kind="real_chivalry"),
                       lambda c: c["units"][0]["effects"][0].update(clock="some_turn_end"),
                       lambda c: c["units"][0]["skills"][0].update(preserve_effects=1),
                       lambda c: c.update(content_snapshot={})):
            config = scenario()
            mutate(config)
            with self.subTest(config=config), self.assertRaises(EngineError):
                validate_config(config)


class LifecycleStandTests(unittest.TestCase):
    def test_pending_movement_survives_restart_and_duplicate_response(self):
        config = scenario()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stand.sqlite3"
            stand = Stand(path)
            created = stand.create_match(config)
            self.assertEqual(created["fidelity"], "mechanics_lab")
            match_id = created["match_id"]
            envelope = stand.get_decision_request(match_id, 0)
            action = next(a for a in envelope["request"]["legal_actions"]
                          if a["kind"] == "attack" and a["to"] == [3, 1] and a["target"] == 2)
            payload = submission(envelope, action["action_id"])
            receipt = stand.submit_action(match_id, payload)
            restarted = Stand(path)
            self.assertEqual(receipt, restarted.submit_action(match_id, payload))
            envelope = restarted.get_decision_request(match_id, 0)
            self.assertEqual(envelope["request"]["observation"]["fidelity"], "mechanics_lab")
            self.assertEqual({a["kind"] for a in envelope["request"]["legal_actions"]}, {"finish_move"})
            restarted.submit_action(match_id, submission(envelope, envelope["request"]["legal_actions"][0]["action_id"]))
            replay = restarted.get_replay(match_id)
            self.assertTrue(verify_replay(replay)["verified"])
            self.assertEqual(replay["final_state"]["lifecycle"]["action_serial"], 1)
            replay["fidelity"] = "synthetic_fixture"
            with self.assertRaises(EngineError):
                verify_replay(replay)

    def test_self_refresh_does_not_open_a_request_for_opponent(self):
        with tempfile.TemporaryDirectory() as temp:
            stand = Stand(Path(temp) / "stand.sqlite3")
            match_id = stand.create_match(scenario())["match_id"]
            envelope = stand.get_decision_request(match_id, 0)
            action = next(a for a in envelope["request"]["legal_actions"] if a.get("skill") == "fixture_self_refresh")
            stand.submit_action(match_id, submission(envelope, action["action_id"]))
            self.assertIsNone(stand.get_decision_request(match_id, 1)["request"])
            self.assertIsNotNone(stand.get_decision_request(match_id, 0)["request"])

    def test_seeded_collection_finishes_inside_bound_and_replays_verify(self):
        config = scenario()
        with tempfile.TemporaryDirectory() as temp:
            stand = Stand(Path(temp) / "stand.sqlite3")
            output = Path(temp) / "collection"
            report = run_selfplay(stand, config, 3, 8, ["heuristic", "random"], output)
            self.assertEqual(report["ruleset"], config["ruleset"])
            self.assertEqual(report["fidelity"], "mechanics_lab")
            self.assertLessEqual(report["decisions"], 3 * decision_bound(config))
            self.assertFalse(report["training"])
            for path in output.glob("episode-*.json"):
                self.assertTrue(verify_replay(json.loads(path.read_text()))["finished"])


if __name__ == "__main__":
    unittest.main()
