import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from parser_engine import ParseVizEngine, GrammarError, EPS  # noqa: E402

EXPR = "E -> E + T | T\nT -> T * F | F\nF -> ( E ) | id"


class EngineTests(unittest.TestCase):
    def run_grammar(self, g, s=""):
        return ParseVizEngine(g).process_all(s)

    def test_left_recursion_expression(self):
        r = self.run_grammar(EXPR, "id + id * id")
        fg = r["final_grammar"]
        self.assertEqual(fg["E"], ["T E'"])
        self.assertEqual(fg["E'"], ["+ T E'", EPS])
        self.assertEqual(fg["T'"], ["* F T'", EPS])

    def test_first_follow_expression(self):
        r = self.run_grammar(EXPR, "id")
        self.assertEqual(r["first_sets"]["E"], ["(", "id"])
        self.assertEqual(r["first_sets"]["E'"], ["+", EPS])
        self.assertEqual(r["follow_sets"]["E"], [")", "$"])
        self.assertEqual(r["follow_sets"]["T"], [")", "+", "$"])
        self.assertEqual(r["follow_sets"]["F"], [")", "*", "+", "$"])
        self.assertTrue(r["is_ll1"])
        self.assertTrue(r["parse_success"])

    def test_reject_with_location(self):
        r = self.run_grammar(EXPR, "id + * id")
        self.assertFalse(r["parse_success"])
        self.assertEqual(r["error"]["index"], 2)
        self.assertEqual(r["error"]["token"], "*")
        self.assertIn("(", r["error"]["expected"])

    def test_missing_paren(self):
        r = self.run_grammar(EXPR, "( id + id")
        self.assertFalse(r["parse_success"])
        self.assertEqual(r["error"]["token"], "$")

    def test_tokenizer_splits_unspaced_input(self):
        r = self.run_grammar(EXPR, "id+id*id")
        self.assertTrue(r["parse_success"])
        self.assertEqual(r["tokens"], ["id", "+", "id", "*", "id"])

    def test_epsilon_empty_string(self):
        r = self.run_grammar("S -> a S b | e", "")
        self.assertTrue(r["parse_success"])
        r = self.run_grammar("S -> a S b | e", "a a b b")
        self.assertTrue(r["parse_success"])
        r = self.run_grammar("S -> a S b | e", "a b b")
        self.assertFalse(r["parse_success"])

    def test_epsilon_base_case_recursion(self):
        # A -> A a | e  must give A -> A' (no stray epsilon symbol in front)
        r = self.run_grammar("A -> A a | e", "a a")
        self.assertEqual(r["final_grammar"]["A"], ["A'"])
        self.assertTrue(r["parse_success"])

    def test_left_factoring_longest_prefix(self):
        r = self.run_grammar("S -> a b c | a b d | a e2 | x", "a b d")
        fg = r["final_grammar"]
        self.assertIn("a S'", fg["S"])
        self.assertTrue(r["is_ll1"])
        self.assertTrue(r["parse_success"])
        self.assertTrue(any(s["common_prefix"] == "a" for s in r["left_factoring_steps"]))
        # nested: b c | b d  under S'
        self.assertTrue(any(s["common_prefix"] == "b" for s in r["left_factoring_steps"]))

    def test_dangling_else_conflict(self):
        g = "S -> i E t S S' | a\nS' -> e2 S | e\nE -> b"
        r = self.run_grammar(g, "i b t a")
        self.assertFalse(r["is_ll1"])
        c = r["conflicts"][0]
        self.assertEqual((c["non_terminal"], c["terminal"], c["kind"]), ("S'", "e2", "FIRST/FOLLOW"))
        self.assertEqual(len(r["conflicts"]), 1)  # no duplicates

    def test_multiple_conflicts(self):
        r = self.run_grammar("S -> A | B\nA -> a | b\nB -> a | b")
        self.assertEqual(len(r["conflicts"]), 2)

    def test_no_false_conflict_for_nullable_production(self):
        # A -> B c ; B -> b | e ; FIRST and FOLLOW overlap on the same production only
        r = self.run_grammar("S -> A a\nA -> b A | e", "b b a")
        self.assertTrue(r["is_ll1"])
        self.assertTrue(r["parse_success"])

    def test_indirect_left_recursion(self):
        g = "S -> A\nA -> S y | z"
        self.assertTrue(self.run_grammar(g, "z y")["parse_success"])
        r = self.run_grammar(g, "z y y y")
        self.assertTrue(r["parse_success"])
        self.assertTrue(any("Substitute" in e for st in r["left_recursion_steps"] for e in st["explain"]))

    def test_ambiguity_probe(self):
        self.assertTrue(self.run_grammar("E -> E + E | id")["ambiguity"]["ambiguous"])
        self.assertFalse(self.run_grammar(EXPR)["ambiguity"]["ambiguous"])

    def test_parse_tree_shape(self):
        r = self.run_grammar(EXPR, "id")
        tree = r["parse_tree"]
        self.assertEqual(tree["label"], "E")
        leaves = []

        def walk(n):
            if not n["children"]:
                leaves.append(n["label"])
            for c in n["children"]:
                walk(c)
        walk(tree)
        self.assertEqual([x for x in leaves if x != EPS], ["id"])

    def test_partial_tree_on_error(self):
        r = self.run_grammar(EXPR, "id + * id")
        self.assertFalse(r["parse_success"])
        self.assertTrue(r["parse_tree"]["children"])

    def test_practice(self):
        eng = ParseVizEngine(EXPR)
        qs = eng.generate_practice_questions(6, seed=3)
        self.assertEqual(len(qs), 6)
        verdicts = [eng.check_prediction(q["test_string"], True)["accepted"] for q in qs]
        self.assertTrue(any(verdicts) and not all(verdicts))
        self.assertTrue(eng.check_prediction("id + id", True)["correct"])
        self.assertFalse(eng.check_prediction("id +", True)["correct"])

    def test_bad_grammar(self):
        with self.assertRaises(GrammarError):
            ParseVizEngine("")
        with self.assertRaises(GrammarError):
            ParseVizEngine("hello world")

    def test_nonterminating_left_recursion_guard(self):
        r = self.run_grammar("A -> A a", "a")
        self.assertFalse(r["parse_success"])


if __name__ == "__main__":
    unittest.main()
