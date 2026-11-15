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
    config = json.loads((ROOT / 'scenarios/guard_lab.json').read_text())
    config['units'][0]['x'], config['units'][0]['y'] = 3, 3
    config['units'][0]['post_attack_move'] = 0
    return config


def attack(config, state):
    a = next(a for a in legal_actions(config, state) if a['kind'] == 'attack' and a['unit'] == 0
             and a['target'] == 3 and a['to'] == [3, 3])
    return apply_action(config, state, a['action_id'])


def unit(state, id):
    return next(u for u in state['battle']['units'] if u['id'] == id)


class GuardTests(unittest.TestCase):
    def test_physical_interception_redirects_damage_with_guard_defense(self):
        c = scenario()
        state, events = attack(c, initial_state(c))
        self.assertEqual(unit(state, 3)['hp'], c['units'][3]['hp'])
        self.assertEqual(unit(state, 2)['hp'], c['units'][2]['hp'] - max(1, c['units'][0]['attack'] - c['units'][2]['defense']))
        self.assertEqual([e['type'] for e in events if e['type'] in ('guard_intercept', 'fixture_damage')],
                         ['guard_intercept', 'fixture_damage'])
        self.assertEqual(next(e for e in events if e['type'] == 'guard_intercept')['protected'], 3)

    def test_magic_guard_and_ignore_guard(self):
        for attack_kind, types, ignore, intercepted in [('magic', ['physical'], False, False),
                                                         ('magic', ['magic'], False, True),
                                                         ('physical', ['physical'], True, False)]:
            c = scenario()
            c['units'][0]['attack_kind'] = attack_kind
            c['units'][0]['ignore_guard'] = ignore
            c['units'][2]['guard']['types'] = types
            state, events = attack(c, initial_state(c))
            self.assertEqual(any(e['type'] == 'guard_intercept' for e in events), intercepted)
            self.assertEqual(next(e for e in events if e['type'] == 'fixture_damage')['target'], 2 if intercepted else 3)

    def test_range_dead_guard_and_deterministic_tie(self):
        c = scenario()
        c['units'][2]['guard']['range'] = 1
        state, events = attack(c, initial_state(c))
        self.assertFalse(any(e['type'] == 'guard_intercept' for e in events))
        c['units'][2]['guard']['range'] = 2
        c['units'][2]['hp'] = 1
        state, events = attack(c, initial_state(c))
        self.assertEqual(unit(state, 2)['hp'], 0)
        self.assertEqual(unit(state, 3)['hp'], c['units'][3]['hp'])

    def test_invalid_guard_schema_fails_closed(self):
        for change in (lambda c: c['units'][2]['guard'].update(range=0),
                       lambda c: c['units'][2]['guard'].update(types=['physical', 'physical']),
                       lambda c: c['units'][2].update(ignore_guard=1),
                       lambda c: c['units'][2]['guard'].update(types=['fixed']),
                       lambda c: c['units'][2].update(extra_guard=True)):
            c = scenario()
            change(c)
            with self.assertRaises(EngineError):
                validate_config(c)

    def test_stand_replay_interception(self):
        with tempfile.TemporaryDirectory() as tmp:
            stand = Stand(Path(tmp) / 'stand.db')
            c = scenario()
            match_id = stand.create_match(c)['match_id']
            envelope = stand.get_decision_request(match_id, 0)
            action = next(a for a in envelope['request']['legal_actions'] if a['kind'] == 'attack' and a['target'] == 3 and a['to'] == [3, 3])
            stand.submit_action(match_id, submission(envelope, action['action_id']))
            replay = stand.get_replay(match_id)
            self.assertTrue(verify_replay(replay)['verified'])
            self.assertTrue(any(e['type'] == 'guard_intercept' for e in replay['decisions'][0]['receipt']['events']))

if __name__ == '__main__':
    unittest.main()
