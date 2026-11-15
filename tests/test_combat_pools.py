import copy
import json
from pathlib import Path
import tempfile
import unittest

from apex_engine.errors import EngineError
from apex_engine.game import ROOT, apply_action, initial_state, legal_actions, validate_config
from apex_engine.stand import Stand, verify_replay
from apex_engine.agents import submission


def scenario():
    c = json.loads((ROOT / 'scenarios/combat_pools_lab.json').read_text())
    c['units'][0]['x'], c['units'][0]['y'] = 3, 3
    c['units'][0]['post_attack_move'] = 0
    return c


def attack(c):
    state = initial_state(c)
    a = next(a for a in legal_actions(c, state) if a['kind'] == 'attack' and a['unit'] == 0
             and a['target'] == 3 and a['to'] == [3, 3])
    return apply_action(c, state, a['action_id'])


def unit(state, id):
    return next(u for u in state['battle']['units'] if u['id'] == id)


class CombatPoolsTests(unittest.TestCase):
    def test_full_tank_intercepts_both_damage_types(self):
        for kind in ('physical', 'magic'):
            c = scenario()
            c['units'][0]['attack_kind'] = kind
            state, events = attack(c)
            self.assertEqual(next(e['guard'] for e in events if e['type'] == 'guard_intercept'), 2)
            self.assertEqual(unit(state, 3)['hp'], c['units'][3]['hp'])

    def test_specialist_only_intercepts_declared_type(self):
        for guarded in ('physical', 'magic'):
            c = scenario()
            c['units'][2]['guard']['types'] = [guarded]
            for attack_kind in ('physical', 'magic'):
                c['units'][0]['attack_kind'] = attack_kind
                state, events = attack(c)
                self.assertEqual(any(e['type'] == 'guard_intercept' for e in events), guarded == attack_kind)

    def test_soldier_pool_absorbs_then_hero_pool_loses_remainder(self):
        c = scenario()
        c['units'][2]['soldier_hp'] = 2
        c['units'][2]['hero_hp'] = 38
        c['units'][2]['hp'] = 40
        state, events = attack(c)
        defender = unit(state, 2)
        damage = max(1, c['units'][0]['attack'] - c['units'][2]['defense'])
        self.assertEqual(defender['soldier_remaining'], 0)
        self.assertEqual(defender['hero_remaining'], 38 - (damage - 2))
        self.assertEqual(defender['hp'], defender['hero_remaining'] + defender['soldier_remaining'])
        self.assertEqual(next(e for e in events if e['type'] == 'fixture_damage_pools')['soldier'], 2)

    def test_ignore_guard_hits_original_pools_and_elimination(self):
        c = scenario()
        c['units'][0]['ignore_guard'] = True
        c['units'][3]['hero_hp'] = 1
        c['units'][3]['soldier_hp'] = 0
        c['units'][3]['hp'] = 1
        state, events = attack(c)
        self.assertEqual(unit(state, 3)['hero_remaining'], 0)
        self.assertEqual(unit(state, 2)['hp'], c['units'][2]['hp'])
        self.assertFalse(any(e['type'] == 'guard_intercept' for e in events))

    def test_invalid_pool_or_unmodelled_stats_rejected(self):
        for change in (lambda c: c['units'][0].update(hero_hp=0),
                       lambda c: c['units'][0].update(soldier_hp=-1),
                       lambda c: c['units'][0].update(hp=41),
                       lambda c: c['units'][0].update(crit=10)):
            c = scenario()
            change(c)
            with self.assertRaises(EngineError):
                validate_config(c)

    def test_replay_contains_same_damage_pools(self):
        c = scenario()
        with tempfile.TemporaryDirectory() as tmp:
            stand = Stand(Path(tmp) / 'stand.db')
            match = stand.create_match(c)['match_id']
            request = stand.get_decision_request(match, 0)
            action = next(a for a in request['request']['legal_actions'] if a['kind'] == 'attack'
                          and a['target'] == 3 and a['to'] == [3, 3])
            stand.submit_action(match, submission(request, action['action_id']))
            replay = stand.get_replay(match)
            self.assertTrue(verify_replay(replay)['verified'])
            self.assertEqual(unit(replay['final_state'], 2)['hp'],
                             unit(replay['final_state'], 2)['hero_remaining'] + unit(replay['final_state'], 2)['soldier_remaining'])

if __name__ == '__main__':
    unittest.main()
