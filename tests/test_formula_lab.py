import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from apex_engine.errors import EngineError
from apex_engine.formula_lab import check_cases, damage, stat
from apex_engine.game import ROOT


CASES = ROOT / 'data/mechanics/formula_research_cases.json'


class FormulaLabTests(unittest.TestCase):
    def test_recorded_calculator_cases_match(self):
        self.assertEqual(len(check_cases(CASES)), 4)

    def test_panel_percent_uses_white_not_equipped_total(self):
        result = stat(dict(white=1000, equipment_flat=100, enchant_flat=20,
                           enchant_percent=5, set_percent=5, battle_percent=25))
        self.assertEqual(result['panel'], Decimal(1220))
        self.assertEqual(result['battle'], Decimal(1525))

    def test_groups_multiply_and_defense_applies_before_ignoring(self):
        cases = json.loads(CASES.read_text())['cases']
        basic = cases[1]['input']['modifiers']
        grouped = {**basic, 'general_damage_percent': 20, 'skill_damage_percent': 10}
        modified = {**grouped, 'defense_class_percent': 20, 'ignore_defense_percent': 20}
        self.assertEqual(damage(1000, 400, basic)['total'], 6000)
        self.assertEqual(damage(1000, 400, grouped)['total'], 7920)
        self.assertEqual(damage(1000, 400, modified)['total'], Decimal('8131.2'))
        self.assertEqual(damage(1000, 400, modified)['critical_total'], Decimal('10570.56'))

    def test_cases_fail_when_observation_is_tampered(self):
        payload = json.loads(CASES.read_text())
        payload['cases'][2]['expected']['total'] = '8000'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cases.json'
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(EngineError, 'mismatch'):
                check_cases(path)

    def test_unsupported_fields_and_invalid_values_fail(self):
        payload = json.loads(CASES.read_text())['cases'][1]['input']['modifiers']
        for wrong in ({**payload, 'hidden_crit': 10}, {**payload, 'strikes': 0},
                      {**payload, 'ignore_defense_percent': 101}, {**payload, 'terrain_percent': 'NaN'}):
            with self.assertRaises(EngineError):
                damage(1000, 400, wrong)
        with self.assertRaises(EngineError):
            stat(dict(white=True, equipment_flat=1))


if __name__ == '__main__':
    unittest.main()
