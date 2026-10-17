import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'AbnormalMaya'/'scripts'))
from abnormal_maya import history,preferences


class HistoryTests(unittest.TestCase):
    def test_undo_redo_and_branch(self):
        h=history.History();h.push({'n':[0]});h.push({'n':[1]})
        self.assertEqual(h.move(-1,{'n':[1]}),{'n':[0]})
        self.assertEqual(h.move(1,{'n':[0]}),{'n':[1]})
        h.move(-1,{'n':[1]});h.push({'n':[2]})
        self.assertIsNone(h.move(1,{'n':[2]}))

    def test_external_state_captured_before_undo(self):
        h=history.History();h.push({'n':0})
        self.assertEqual(h.move(-1,{'n':1}),{'n':0})
        self.assertEqual(h.move(1,{'n':0}),{'n':1})

    def test_snapshots_are_independent_and_bounded(self):
        h=history.History(2);value={'mask':{0:.5}}
        h.push(value);value['mask'][0]=1
        self.assertEqual(h.states[0]['mask'][0],.5)
        h.push(value);h.push({'mask':{}})
        self.assertEqual(len(h.states),2)
        state=h.move(-1,{'mask':{}});state['mask'].clear()
        self.assertTrue(h.states[0]['mask'])


class PreferenceTests(unittest.TestCase):
    def test_defaults_and_unknown_fields(self):
        self.assertEqual(preferences.validate({}),preferences.DEFAULTS)
        self.assertNotIn('unknown',preferences.validate({'unknown':'ignored'}))

    def test_valid_values(self):
        values=preferences.validate({'selection_mode':'Lasso','normal_size':2,'shortcuts_enabled':False})
        self.assertEqual(values['selection_mode'],'Lasso');self.assertFalse(values['shortcuts_enabled'])

    def test_invalid_types_ranges_and_nan(self):
        for value in [{'strength':2},{'iterations':0},{'space':'Unknown'},
                      {'shortcuts_enabled':'false'},{'normal_size':float('nan')},
                      {'selection_radius':True},[],None]:
            with self.assertRaises(ValueError): preferences.validate(value)


if __name__=='__main__': unittest.main()
