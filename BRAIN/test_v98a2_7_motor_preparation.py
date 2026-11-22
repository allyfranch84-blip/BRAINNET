import unittest
from capability_lab import bounded_linear_points
from parser_contract import parse_supervised_mouse_move

class MotorPreparationTests(unittest.TestCase):
    def test_linear_path_is_deterministic_and_inside(self):
        points=bounded_linear_points((10,10),30,0,(0,0,60,20))
        self.assertEqual(points,[(x,10) for x in range(10,41)])
        self.assertEqual(points,bounded_linear_points((10,10),30,0,(0,0,60,20)))
    def test_path_leaving_region_is_rejected(self):
        with self.assertRaises(ValueError): bounded_linear_points((10,10),30,0,(0,0,40,20))
    def test_both_forms_remain_proposals(self):
        for text in ('mova o mouse 30 pixels para a direita, sem clicar', 'movimente o mouse lentamente 30 pixels para a direita sem clicar'):
            proposal=parse_supervised_mouse_move(text)
            self.assertEqual((proposal['dx'],proposal['dy']),(30,0))
            self.assertFalse(proposal['execution_authorized'])
    def test_negation_does_not_create_proposal(self):
        self.assertIsNone(parse_supervised_mouse_move('não mova o mouse 30 pixels para a direita, sem clicar'))
if __name__ == '__main__': unittest.main()
