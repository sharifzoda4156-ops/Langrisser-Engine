import copy
import json
from pathlib import Path
import tempfile
import unittest

from apex_engine.aoe_terrain_probe import check_cases, evaluate
from apex_engine.errors import EngineError
from apex_engine.game import ROOT


TEMPLATE = ROOT / "data/mechanics/aoe_terrain_probe_template.json"


class AoeTerrainProbeTests(unittest.TestCase):
    def setUp(self):
        self.case = json.loads(TEMPLATE.read_text())["cases"][0]

    def measured(self, plain, terrain):
        case = copy.deepcopy(self.case)
        case["source"] = "https://example.org/recorded-pair"
        case["patch"] = "2026-11-15"
        case["controls"] = {key: True for key in case["controls"]}
        case["observed"] = {"plain": dict(hero=plain[0], soldier=plain[1]),
                            "terrain": dict(hero=terrain[0], soldier=terrain[1])}
        return case

    def test_template_never_passes_as_observation(self):
        report = check_cases(TEMPLATE)[0]
        self.assertEqual(report["result"], "awaiting_observation")
        self.assertEqual(report["predictions"]["plain"], {"hero": "1800.0", "soldier": "1800.0"})
        self.assertEqual(report["predictions"]["with_terrain"], {"hero": "1560.00", "soldier": "1560.00"})

    def test_pair_distinguishes_both_hypotheses_and_component_defense(self):
        self.assertEqual(evaluate(self.measured((1800, 1800), (1560, 1560)))["result"],
                         "supports_terrain")
        self.assertEqual(evaluate(self.measured((1800, 1800), (1800, 1800)))["result"],
                         "supports_no_terrain")
        case = self.measured((1800, 2100), (1560, 1920))
        case["input"]["soldier_defense"] = 300
        self.assertEqual(evaluate(case)["result"], "supports_terrain")

    def test_confounds_and_wrong_baseline_do_not_support_a_rule(self):
        case = self.measured((1800, 1800), (1560, 1560))
        case["controls"]["no_tile_triggered_extras"] = False
        self.assertEqual(evaluate(case)["result"], "uncontrolled")
        case["controls"]["no_tile_triggered_extras"] = True
        case["observed"]["plain"]["soldier"] = "1700"
        self.assertEqual(evaluate(case)["result"], "baseline_mismatch")

    def test_tolerance_cannot_turn_ambiguous_pair_into_evidence(self):
        case = self.measured((1800, 1800), (1800, 1800))
        case["input"]["hero_defense"] = 1
        case["input"]["soldier_defense"] = 1
        case["input"]["terrain_percent"] = 1
        case["observed"]["plain"] = {"hero": "2997", "soldier": "2997"}
        case["observed"]["terrain"] = {"hero": "2997", "soldier": "2997"}
        self.assertEqual(evaluate(case)["result"], "inconclusive")
        case = self.measured((1800, 1800), (1700, 1700))
        self.assertEqual(evaluate(case)["result"], "inconclusive")

    def test_measured_cases_require_provenance_and_strict_shape(self):
        case = self.measured((1800, 1800), (1560, 1560))
        case["source"] = "unmeasured"
        with self.assertRaises(EngineError):
            evaluate(case)
        case["source"] = "https://example.org/recorded-pair"
        case["observed"]["terrain"]["total"] = 3120
        with self.assertRaises(EngineError):
            evaluate(case)
        case["observed"]["terrain"].pop("total")
        case["input"]["max_error"] = 100
        with self.assertRaises(EngineError):
            evaluate(case)

    def test_duplicate_case_ids_are_rejected(self):
        payload = json.loads(TEMPLATE.read_text())
        payload["cases"].append(copy.deepcopy(payload["cases"][0]))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(EngineError, "duplicate"):
                check_cases(path)


if __name__ == "__main__":
    unittest.main()
