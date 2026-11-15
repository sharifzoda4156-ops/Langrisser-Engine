import unittest

from apex_engine.errors import EngineError
from apex_engine.hit_sequence_lab import simulate_hits


class HitSequenceLabTests(unittest.TestCase):
    def test_lana_example_spends_twenty_hits_on_ten_soldiers(self):
        hit = {"source": "hero", "to_soldier": 100, "to_hero": 100}
        result = simulate_hits([180] * 10, 100, [hit] * 20)
        self.assertEqual(result["soldier_hp"], [0] * 10)
        self.assertEqual(result["hero_hp"], 100)
        self.assertEqual(sum(event["excess"] for event in result["events"]), 200)
        self.assertTrue(all(event["target"].startswith("soldier:")
                            for event in result["events"]))

    def test_order_and_four_damage_directions_are_explicit(self):
        hero = {"source": "hero", "to_soldier": 10, "to_hero": 4}
        soldier = {"source": "soldier", "to_soldier": 3, "to_hero": 8}
        first = simulate_hits([5], 20, [soldier, hero])
        second = simulate_hits([5], 20, [hero, soldier])
        self.assertEqual((first["soldier_hp"], first["hero_hp"]), ([0], 20))
        self.assertEqual((second["soldier_hp"], second["hero_hp"]), ([0], 12))
        self.assertEqual(first["events"][1]["excess"], 8)

    def test_variable_soldier_count_and_unsupported_inputs(self):
        hit = {"source": "soldier", "to_soldier": 1, "to_hero": 3}
        self.assertEqual(simulate_hits([], 5, [hit])["hero_hp"], 2)
        self.assertEqual(simulate_hits([1] * 12, 5, [hit])["soldier_hp"], [0] + [1] * 11)
        for soldiers, hp, hits in [([True], 5, [hit]), ([1] * 13, 5, [hit]),
                                   ([], -1, []), ([], 1, [{**hit, "rounding": "floor"}]),
                                   ([], 1, [{**hit, "to_hero": -1}])]:
            with self.subTest(soldiers=soldiers, hp=hp, hits=hits):
                with self.assertRaises(EngineError):
                    simulate_hits(soldiers, hp, hits)


if __name__ == "__main__":
    unittest.main()
