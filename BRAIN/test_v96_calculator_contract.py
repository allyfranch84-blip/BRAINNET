import ast
import unittest

from htn_planner import compile_primitives, parse_objectives

REQUEST = 'Abra o Notepad e escreva o código Python de uma calculadora com interface.'
CODE = '''import tkinter as tk
root = tk.Tk()
tk.Label(root, text="Calculadora").pack()
root.mainloop()
'''

class CalculatorArtifactTests(unittest.TestCase):
    def test_generated_artifact_reaches_proposed_editor_step(self):
        goals = parse_objectives(REQUEST)
        seen = []
        plan = compile_primitives(goals, lambda instruction: (seen.append(instruction), CODE)[1])
        writes = [p for p in plan['pipeline'] if p['p'] == 'TYPE']
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]['text'], CODE.strip())
        self.assertNotEqual(writes[0]['text'], seen[0])
        ast.parse(writes[0]['text'])
        # Simulated editor observation only: this is not physical execution.
        fake_editor = {'content': writes[0]['text']}
        self.assertEqual(fake_editor['content'], CODE.strip())

    def test_unavailable_generator_blocks_plan(self):
        with self.assertRaises(ValueError):
            compile_primitives(parse_objectives(REQUEST))

    def test_bad_artifacts_are_rejected(self):
        for source in ('', 'o código Python de uma calculadora', 'print(1)', 'import tkinter as tk'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                compile_primitives(parse_objectives(REQUEST), lambda _: source)

    def test_generator_failure_propagates(self):
        def unavailable(_):
            raise RuntimeError('indisponível')
        with self.assertRaises(RuntimeError):
            compile_primitives(parse_objectives(REQUEST), unavailable)

    def test_quoted_content_remains_literal(self):
        goals = parse_objectives('abra o notepad e escreva "código Python"')
        plan = compile_primitives(goals)
        self.assertEqual(plan['pipeline'][-1]['text'], 'código Python')

if __name__ == '__main__':
    unittest.main()
