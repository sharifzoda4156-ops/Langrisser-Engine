"""Behavioral checks for regional isolation, explicit previews and stand binding."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from apex_engine.agents import run_selfplay, submission
from apex_engine.content import (bind_snapshot, build_preview, build_snapshot, ref_for,
                                 seal, verify_snapshot)
from apex_engine.errors import EngineError
from apex_engine.game import ROOT, initial_state, state_hash, validate_config
from apex_engine.stand import Stand, verify_replay

DATA = ROOT / "data" / "content"


def load(name):
    return json.loads((DATA / name).read_text())


def catalog():
    return load("fixture_catalog.json")


def manifest(region="global"):
    return load(f"fixture_{region}_manifest.json")


def config():
    return json.loads((ROOT / "scenarios" / "protocol_fixture.json").read_text())


def global_snapshot():
    return build_snapshot(catalog(), manifest())


def china_snapshot():
    return build_snapshot(catalog(), manifest("cn"))


def changes():
    return load("fixture_preview_changes.json")


def reseal(snapshot):
    return seal({k: v for k, v in snapshot.items() if k != "content_digest"})


class SnapshotTests(unittest.TestCase):
    def test_content_is_pinned_independent_of_catalog_order(self):
        original = global_snapshot()
        data = catalog()
        data["entries"].reverse()
        self.assertEqual(original, build_snapshot(data, manifest()))
        data["entries"][0]["payload"]["attack"] = 777
        self.assertTrue(verify_snapshot(original))

    def test_unknown_or_multiple_active_revisions_fail(self):
        for ref in ({"id": "fixture_striker", "revision": "v999"},
                    {"id": "fixture_striker", "revision": "v1"}):
            selected = manifest()
            selected["entries"].append(ref)
            with self.subTest(ref=ref), self.assertRaises(EngineError):
                build_snapshot(catalog(), selected)

    def test_global_rejects_unreleased_and_unannounced_content(self):
        for ref in ({"id": "fixture_striker", "revision": "v2"}, changes()[0]):
            selected = manifest()
            selected["entries"] = [r for r in selected["entries"] if r["id"] != ref["id"]] + [ref]
            with self.subTest(ref=ref), self.assertRaisesRegex(EngineError, "unavailable"):
                build_snapshot(catalog(), selected)

    def test_release_boundary_and_expiration(self):
        data = catalog()
        selected = manifest()
        selected["entries"][0]["revision"] = "v2"
        selected["as_of"] = "2000-02-01"
        self.assertTrue(verify_snapshot(build_snapshot(data, selected)))
        data["entries"][-1]["releases"]["global"]["until"] = "2000-02-02"
        selected["as_of"] = "2000-02-02"
        with self.assertRaisesRegex(EngineError, "unavailable"):
            build_snapshot(data, selected)

    def test_no_implicit_latest_revision_or_calendar_shift(self):
        selected = manifest()
        selected["as_of"] = "2026-11-14"
        snapshot = build_snapshot(catalog(), selected)
        striker = next(e for e in snapshot["entries"] if e["id"] == "fixture_striker")
        self.assertEqual(striker["revision"], "v1")
        self.assertNotIn("fixture_vanguard", [e["id"] for e in snapshot["entries"]])

    def test_digest_detects_mutation(self):
        snapshot = global_snapshot()
        snapshot["entries"][0]["payload"]["attack"] = 777
        with self.assertRaisesRegex(EngineError, "digest"):
            verify_snapshot(snapshot)

    def test_invalid_metadata_and_malformed_inputs_are_rejected(self):
        for mutate in (lambda m: m.update(schema_version=True),
                       lambda m: m.update(as_of="2000-02-30"),
                       lambda m: m.update(mode="global_preview"),
                       lambda m: m.update(patch=""),
                       lambda m: m.update(extra=True)):
            selected = manifest()
            mutate(selected)
            with self.subTest(selected=selected), self.assertRaises(EngineError):
                build_snapshot(catalog(), selected)
        for value in (None, [], {}, {"schema_version": 1}):
            with self.subTest(value=value), self.assertRaises(EngineError):
                verify_snapshot(value)
        data = catalog()
        data["entries"][0]["kind"] = []
        with self.assertRaises(EngineError):
            build_snapshot(data, manifest())

    def test_dependency_revision_and_cycle_checks(self):
        for dependencies in ([{"id": "fixture_sentinel", "revision": "v999"}],
                             [{"id": "fixture_striker", "revision": "v1"}]):
            data = catalog()
            data["entries"][0]["dependencies"] = dependencies
            with self.subTest(dependencies=dependencies), self.assertRaises(EngineError):
                build_snapshot(data, manifest())

    def test_duplicate_catalog_revision_rejected(self):
        data = catalog()
        data["entries"].append(copy.deepcopy(data["entries"][0]))
        with self.assertRaisesRegex(EngineError, "duplicate catalog"):
            build_snapshot(data, manifest())


class PreviewTests(unittest.TestCase):
    def test_imports_only_declared_candidate(self):
        baseline, source = global_snapshot(), china_snapshot()
        preview = build_preview(baseline, source, changes(), "fixture-preview")
        entries = {e["id"]: e for e in preview["entries"]}
        self.assertIn("fixture_vanguard", entries)
        self.assertEqual(entries["fixture_striker"]["revision"], "v1")
        self.assertEqual(preview["lineage"]["baseline"], baseline)
        self.assertEqual(preview["lineage"]["source"], source)
        self.assertEqual(verify_snapshot(preview)["mode"], "global_preview")

    def test_preview_and_lineage_do_not_share_mutable_entries(self):
        preview = build_preview(global_snapshot(), china_snapshot(), changes(), "fixture-preview")
        baseline_before = copy.deepcopy(preview["lineage"]["baseline"])
        next(e for e in preview["entries"] if e["id"] == "fixture_striker")["payload"]["attack"] += 1
        self.assertEqual(baseline_before, preview["lineage"]["baseline"])

    def test_explicit_override_changes_only_selected_revision(self):
        selected = [{"id": "fixture_striker", "revision": "v2"}]
        preview = build_preview(global_snapshot(), china_snapshot(), selected, "fixture-override")
        self.assertEqual(next(e for e in preview["entries"] if e["id"] == "fixture_striker")["revision"], "v2")
        self.assertNotIn("fixture_vanguard", [e["id"] for e in preview["entries"]])

    def test_undeclared_payload_changes_rejected_even_after_rehash(self):
        preview = build_preview(global_snapshot(), china_snapshot(), changes(), "fixture-preview")
        next(e for e in preview["entries"] if e["id"] == "fixture_striker")["payload"]["attack"] = 999
        with self.assertRaisesRegex(EngineError, "undeclared"):
            verify_snapshot(reseal(preview))

    def test_preview_mode_cannot_be_relabelled_as_global_live(self):
        preview = build_preview(global_snapshot(), china_snapshot(), changes(), "fixture-preview")
        preview.update(mode="global_live", lineage=None)
        with self.assertRaisesRegex(EngineError, "unavailable"):
            verify_snapshot(reseal(preview))

    def test_unlisted_dependency_is_not_imported_automatically(self):
        data = catalog()
        candidate = next(e for e in data["entries"] if e["id"] == "fixture_vanguard")
        candidate["dependencies"] = [{"id": "fixture_striker", "revision": "v2"}]
        source = build_snapshot(data, manifest("cn"))
        with self.assertRaisesRegex(EngineError, "missing exact dependency"):
            build_preview(global_snapshot(), source, changes(), "fixture-preview")
        preview = build_preview(global_snapshot(), source, changes() + candidate["dependencies"], "fixture-preview")
        self.assertTrue(verify_snapshot(preview))

    def test_baseline_dependents_cannot_silently_follow_an_override(self):
        data = catalog()
        data["entries"][1]["dependencies"] = [{"id": "fixture_striker", "revision": "v1"}]
        baseline = build_snapshot(data, manifest())
        with self.assertRaisesRegex(EngineError, "missing exact dependency"):
            build_preview(baseline, china_snapshot(), [{"id": "fixture_striker", "revision": "v2"}], "fixture-preview")

    def test_incompatible_sources_and_nested_previews_fail(self):
        baseline, source = global_snapshot(), china_snapshot()
        for mutate in (lambda s: s.update(ruleset="some-other-ruleset"),
                       lambda s: s.update(mode="global_live", region="global")):
            changed = copy.deepcopy(source)
            mutate(changed)
            with self.subTest(changed=changed), self.assertRaises(EngineError):
                build_preview(baseline, reseal(changed), changes(), "fixture-preview")
        preview = build_preview(baseline, source, changes(), "fixture-preview")
        with self.assertRaisesRegex(EngineError, "nested"):
            build_preview(preview, source, changes(), "fixture-preview-2")

    def test_conflicting_shared_revision_and_duplicate_changes_fail(self):
        source = china_snapshot()
        next(e for e in source["entries"] if e["id"] == "fixture_sentinel")["payload"]["attack"] += 1
        with self.assertRaisesRegex(EngineError, "differs across"):
            build_preview(global_snapshot(), reseal(source), changes(), "fixture-preview")
        with self.assertRaisesRegex(EngineError, "only once"):
            build_preview(global_snapshot(), china_snapshot(), changes() * 2, "fixture-preview")


class BindingTests(unittest.TestCase):
    def test_snapshot_is_bound_to_every_hero_map_and_draft(self):
        snapshot = global_snapshot()
        baseline = bind_snapshot(config(), snapshot)
        self.assertEqual(validate_config(baseline), baseline)
        for mutate in (lambda c: c["boxes"][0][0].update(attack=999),
                       lambda c: c["map"]["costs"].__setitem__(0, 2),
                       lambda c: c["draft"].update(bans_per_side=0)):
            changed = copy.deepcopy(baseline)
            mutate(changed)
            with self.subTest(changed=changed), self.assertRaises(EngineError):
                validate_config(changed)

    def test_new_candidate_is_allowed_only_with_matching_preview(self):
        preview = build_preview(global_snapshot(), china_snapshot(), changes(), "fixture-preview")
        candidate = next(e["payload"] for e in preview["entries"] if e["id"] == "fixture_vanguard")
        scenario = config()
        scenario["boxes"][0][0] = candidate
        with self.assertRaisesRegex(EngineError, "not in the frozen snapshot"):
            bind_snapshot(scenario, global_snapshot())
        self.assertTrue(bind_snapshot(scenario, preview))

    def test_unsupported_mechanics_rejected_even_if_not_picked(self):
        data = catalog()
        data["entries"][0]["mechanics"].append("unimplemented.fixture.guard")
        snapshot = build_snapshot(data, manifest())
        with self.assertRaisesRegex(EngineError, "unsupported executable mechanics"):
            bind_snapshot(config(), snapshot)

    def test_unused_candidate_cannot_hide_unsupported_payload_fields(self):
        data = catalog()
        next(e for e in data["entries"] if e["id"] == "fixture_vanguard")["payload"]["unknown_talent"] = True
        preview = build_preview(global_snapshot(), build_snapshot(data, manifest("cn")),
                                changes(), "fixture-preview")
        with self.assertRaisesRegex(EngineError, "fixture hero requires"):
            bind_snapshot(config(), preview)

    def test_real_release_metadata_cannot_be_executed_as_fixture(self):
        snapshot = build_snapshot(load("release_evidence_catalog.json"),
                                  load("release_evidence_global_manifest.json"))
        self.assertEqual(verify_snapshot(snapshot)["fidelity"], "release_metadata")
        with self.assertRaisesRegex(EngineError, "not implemented"):
            bind_snapshot(config(), snapshot)
        forged = copy.deepcopy(snapshot)
        forged["ruleset"] = "protocol-fixture-v0"
        with self.assertRaisesRegex(EngineError, "not implemented"):
            bind_snapshot(config(), reseal(forged))

    def test_same_game_position_different_snapshot_has_different_hash(self):
        plain = config()
        bound = bind_snapshot(plain, global_snapshot())
        self.assertNotEqual(state_hash(plain, initial_state(plain)), state_hash(bound, initial_state(bound)))

    def test_stand_restart_observation_and_replay_preserve_lineage(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "stand.sqlite3"
            stand = Stand(database)
            snapshot = build_preview(global_snapshot(), china_snapshot(), changes(), "fixture-preview")
            bound = bind_snapshot(config(), snapshot)
            created = stand.create_match(bound)
            self.assertEqual(created["experiment"]["mode"], "global_preview")
            bound["content_snapshot"]["mode"] = "invalid-after-create"
            restarted = Stand(database)
            request = restarted.get_decision_request(created["match_id"], 0)
            self.assertEqual(request["request"]["observation"]["experiment"]["content_digest"], snapshot["content_digest"])
            restarted.submit_action(created["match_id"], submission(
                request, request["request"]["legal_actions"][0]["action_id"]))
            replay = restarted.get_replay(created["match_id"])
            self.assertTrue(verify_replay(replay)["verified"])
            replay["config"]["content_snapshot"]["entries"][0]["payload"]["attack"] = 999
            with self.assertRaises(EngineError):
                verify_replay(replay)

    def test_invalid_binding_never_creates_a_match(self):
        with tempfile.TemporaryDirectory() as temp:
            stand = Stand(Path(temp) / "stand.sqlite3")
            scenario = config()
            scenario["content_snapshot"] = global_snapshot()
            scenario["boxes"][0][0]["attack"] = 999
            with self.assertRaises(EngineError):
                stand.create_match(scenario)
            with stand.connection() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM matches").fetchone()[0], 0)

    def test_collection_report_labels_its_region_and_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_selfplay(Stand(Path(temp) / "stand.sqlite3"),
                                  bind_snapshot(config(), global_snapshot()), 1, 5,
                                  ["heuristic", "random"], Path(temp) / "run")
            self.assertEqual(report["experiment"]["mode"], "global_live")
            self.assertEqual(report["experiment"]["fidelity"], "synthetic_fixture")
            self.assertFalse(report["training"])


class ContentCLITests(unittest.TestCase):
    def call(self, *args):
        return subprocess.run([sys.executable, "-m", "apex_engine", *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True, timeout=15)

    def test_build_verify_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "snapshot.json"
            args = ("content", "build", "--catalog", DATA / "fixture_catalog.json", "--manifest",
                    DATA / "fixture_global_manifest.json", "--output", output)
            result = self.call(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            before = output.read_bytes()
            self.assertEqual(self.call(*args).returncode, 2)
            self.assertEqual(before, output.read_bytes())
            verified = self.call("content", "verify", output)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertTrue(json.loads(verified.stdout)["verified"])

    def test_metadata_command_does_not_create_database(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "never-created.sqlite3"
            result = self.call("--db", database, "content", "build", "--catalog",
                               DATA / "release_evidence_catalog.json", "--manifest",
                               DATA / "release_evidence_global_manifest.json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["fidelity"], "release_metadata")
            self.assertFalse(database.exists())


if __name__ == "__main__":
    unittest.main()
