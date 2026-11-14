import copy
import json
from pathlib import Path
import tempfile
import unittest

from apex_engine.errors import EngineError
from apex_engine.game import ROOT, apply_action, initial_state, legal_actions, validate_config
from apex_engine.agents import run_selfplay
from apex_engine.stand import Stand, verify_replay


def scenario():
    c = json.loads((ROOT / 'scenarios/action_lifecycle_lab.json').read_text())
    c['ruleset'] = 'terrain-lab-v1'
    c['map']['terrain'] = ['fixture_desert'] * 25
    c['map']['profiles'] = {'fixture_cavalry': {'fixture_desert': 2}, 'fixture_infantry': {'fixture_desert': 1}}
    for u in c['units']:
        u['movement_profile'] = 'fixture_cavalry'
    return c


class TerrainTests(unittest.TestCase):
    def test_desert_cost_changes_reachable_destinations_and_paths(self):
        c = scenario()
        state = initial_state(c)
        mounted = [a for a in legal_actions(c, state) if a['unit'] == 0 and a['kind'] == 'wait']
        self.assertFalse(any(a['to'] == [2, 1] for a in mounted))
        c['units'][0]['movement_profile'] = 'fixture_infantry'
        foot = [a for a in legal_actions(c, initial_state(c)) if a['unit'] == 0 and a['kind'] == 'wait']
        self.assertTrue(any(a['to'] == [2, 1] and len(a['path']) == 3 for a in foot))

    def test_post_attack_move_uses_same_terrain_profile(self):
        c = scenario()
        c['units'][0]['x'] = 3
        state = initial_state(c)
        action = next(a for a in legal_actions(c, state) if a['unit'] == 0 and a['kind'] == 'attack' and a['to'] == [3, 1] and a['target'] == 2)
        state, _ = apply_action(c, state, action['action_id'])
        moves = legal_actions(c, state)
        self.assertEqual({a['kind'] for a in moves}, {'finish_move'})
        self.assertFalse(any(a['to'] == [1, 1] for a in moves))
        self.assertTrue(any(a['to'] == [2, 1] for a in moves))

    def test_missing_or_invalid_profile_rejected(self):
        for change in (lambda c: c['units'][0].update(movement_profile='fixture_missing'),
                       lambda c: c['map']['profiles']['fixture_cavalry'].clear(),
                       lambda c: c['map']['profiles']['fixture_cavalry'].update(fixture_desert=0)):
            c = scenario()
            change(c)
            with self.assertRaises(EngineError):
                validate_config(c)

    def test_stand_replay_and_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            stand = Stand(Path(tmp) / 'stand.db')
            report = run_selfplay(stand, scenario(), 1, 4, ['heuristic', 'random'], Path(tmp) / 'run')
            self.assertEqual(report['fidelity'], 'mechanics_lab')
            replay = json.loads((Path(tmp) / 'run/episode-00000.json').read_text())
            self.assertTrue(verify_replay(replay)['verified'])

if __name__ == '__main__':
    unittest.main()
