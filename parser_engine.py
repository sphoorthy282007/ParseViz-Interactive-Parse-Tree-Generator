"""
ParseViz engine: grammar transformation, FIRST/FOLLOW, LL(1) table, parsing trace,
parse tree, ambiguity probe and practice-question generation.

Conventions
-----------
* Grammar symbols are separated by whitespace:   E -> E + T | T
* Epsilon can be written  e  ε  eps  epsilon  #  λ  (alone in an alternative)
  or as an empty alternative.  Internally it is the single symbol EPS ('ε').
* Every symbol that appears on a left-hand side is a non-terminal; every other
  symbol is a terminal.  '$' is the end-marker.
"""
import random
import re
from collections import OrderedDict, defaultdict

EPS = "ε"
END = "$"
EPS_ALIASES = {"e", "ε", "eps", "epsilon", "#", "λ", "lambda"}
MAX_TRACE_STEPS = 3000


class GrammarError(ValueError):
    """Raised when the grammar text cannot be understood."""


# --------------------------------------------------------------------------- helpers
def fmt(prod):
    return " ".join(prod)


def rule_str(head, prod):
    return f"{head} → {fmt(prod)}"


def sort_syms(items):
    """Stable display order: normal symbols alphabetically, then ε, then $."""
    return sorted(items, key=lambda x: (x == END, x == EPS, x))


def concat(prod, tail):
    """Append `tail` to a production, dropping a leading ε (ε·X = X)."""
    base = [] if prod == [EPS] else list(prod)
    return base + list(tail) or [EPS]


def dedupe(prods):
    seen, out = set(), []
    for p in prods:
        key = tuple(p)
        if key not in seen:
            seen.add(key)
            out.append(list(p))
    return out


def first_of_seq(seq, first, nts):
    """FIRST of a sentential form. Contains ε iff the whole form is nullable."""
    res = set()
    for s in seq:
        if s == EPS:
            continue
        if s in nts:
            res |= first[s] - {EPS}
            if EPS not in first[s]:
                return res
        else:
            res.add(s)
            return res
    res.add(EPS)
    return res


def common_prefix(prods):
    prefix = []
    for column in zip(*prods):
        if all(sym == column[0] for sym in column):
            prefix.append(column[0])
        else:
            break
    return prefix


class ParseVizEngine:
    def __init__(self, grammar_str):
        self.raw_grammar = grammar_str
        self.grammar = OrderedDict()
        self.start_symbol = None
        self.terminals = set()
        self.terminal_order = []
        self.non_terminals = []
        self.parse_input_grammar(grammar_str)

    # ------------------------------------------------------------------ input
    def parse_input_grammar(self, text):
        arrow = re.compile(r"\s*(?:->|→|::=|:=)\s*")
        for lineno, raw in enumerate((text or "").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            m = arrow.search(line)
            if not m:
                raise GrammarError(f"Line {lineno}: expected a rule like  A -> a B | c  but found '{line}'")
            head = line[: m.start()].strip()
            body = line[m.end():]
            if not head or len(head.split()) != 1:
                raise GrammarError(f"Line {lineno}: the left side must be a single non-terminal, got '{head}'")
            if head in EPS_ALIASES and head != "e":
                raise GrammarError(f"Line {lineno}: '{head}' is reserved for epsilon")
            if self.start_symbol is None:
                self.start_symbol = head
            if head not in self.grammar:
                self.grammar[head] = []
                self.non_terminals.append(head)
            for alt in body.split("|"):
                toks = alt.split()
                if not toks or (len(toks) == 1 and toks[0] in EPS_ALIASES):
                    toks = [EPS]
                self.grammar[head].append(toks)
        if not self.grammar:
            raise GrammarError("The grammar is empty. Enter at least one rule such as  S -> a S | b")
        for head in list(self.grammar):
            self.grammar[head] = dedupe(self.grammar[head])
        for prods in self.grammar.values():
            for prod in prods:
                for sym in prod:
                    if sym != EPS and sym not in self.grammar and sym not in self.terminals:
                        self.terminals.add(sym)
                        self.terminal_order.append(sym)
        self.terminals.add(END)

    # ------------------------------------------------------- left recursion
    def _new_name(self, base, used):
        name = base + "'"
        while name in used:
            name += "'"
        used.add(name)
        return name

    def eliminate_left_recursion(self):
        """Paull's algorithm. Pure immediate recursion needs no substitution."""
        steps = []
        order = list(self.grammar)
        work = OrderedDict((h, [list(p) for p in ps]) for h, ps in self.grammar.items())
        out = OrderedDict()
        used = set(order) | set(self.terminals)

        for i, A in enumerate(order):
            explain, subs = [], []
            prods = work[A]
            original = [rule_str(A, p) for p in prods]

            # 1. substitute earlier non-terminals that start a production (indirect recursion)
            for j in range(i):
                Aj = order[j]
                rewritten, hit = [], False
                for p in prods:
                    if p[0] == Aj:
                        hit = True
                        for q in out[Aj]:
                            rewritten.append(concat(q, p[1:]))
                        subs.append(
                            f"Substitute {Aj} → {' | '.join(fmt(q) for q in out[Aj])} into  {rule_str(A, p)}"
                        )
                    else:
                        rewritten.append(p)
                if hit:
                    prods = dedupe(rewritten)
            if subs:
                explain.append("Indirect recursion check: an earlier non-terminal starts a production, so it is substituted first.")
                explain.extend(subs)
                explain.append("Now " + " | ".join(rule_str(A, p) for p in prods))

            # 2. immediate left recursion
            rec = [p[1:] for p in prods if p[0] == A]
            non = [p for p in prods if p[0] != A]
            useless = [p for p in rec if not p]
            alphas = [p for p in rec if p]

            if not rec:
                out[A] = prods
                steps.append({
                    "non_terminal": A,
                    "type": "No Left Recursion" if not subs else "Indirect Left Recursion Resolved by Substitution",
                    "has_recursion": bool(subs),
                    "original": original,
                    "transformed": [rule_str(A, p) for p in prods],
                    "alphas": [], "betas": [], "new_nt": None,
                    "explain": explain or [f"No production of {A} starts with {A}, nothing to do."],
                })
                continue

            if useless:
                explain.append(f"{A} → {A} is a useless cycle and is removed.")
            if not alphas:
                out[A] = non or prods
                steps.append({
                    "non_terminal": A, "type": "Only trivial recursion removed",
                    "has_recursion": True, "original": original,
                    "transformed": [rule_str(A, p) for p in out[A]],
                    "alphas": [], "betas": [fmt(p) for p in non], "new_nt": None,
                    "explain": explain,
                })
                continue
            if not non:
                out[A] = prods
                steps.append({
                    "non_terminal": A, "type": "Warning: no non-recursive alternative",
                    "has_recursion": True, "original": original,
                    "transformed": [rule_str(A, p) for p in prods],
                    "alphas": [fmt(a) for a in alphas], "betas": [], "new_nt": None,
                    "explain": explain + [
                        f"Every production of {A} starts with {A}, so {A} can never derive a string. "
                        "The rule is left unchanged; add a non-recursive alternative (β)."],
                })
                continue

            new = self._new_name(A, used)
            out[A] = [concat(b, [new]) for b in non]
            out[new] = [concat(a, [new]) for a in alphas] + [[EPS]]
            explain += [
                f"Immediate left recursion: {A} → {A}α | β  with  α ∈ {{{', '.join(fmt(a) for a in alphas)}}}  and  β ∈ {{{', '.join(fmt(b) for b in non)}}}.",
                f"Introduce a new non-terminal {new} for the recursive tail.",
                f"Rewrite  {A} → β {new}  and  {new} → α {new} | ε.",
            ]
            steps.append({
                "non_terminal": A,
                "type": "Immediate Left Recursion Detected",
                "has_recursion": True,
                "original": original,
                "transformed": [rule_str(A, p) for p in out[A]] + [rule_str(new, p) for p in out[new]],
                "alphas": [fmt(a) for a in alphas],
                "betas": [fmt(b) for b in non],
                "new_nt": new,
                "explain": explain,
            })
        return steps, out

    # --------------------------------------------------------- left factoring
    def left_factoring(self, grammar):
        steps = []
        out = OrderedDict()
        used = set(grammar) | set(self.terminals)

        def factor(head, prods, original_nt):
            out[head] = None  # reserve position so helper NTs follow their parent
            prods = [list(p) for p in prods]
            did_factor = False
            while True:
                groups = OrderedDict()
                for p in prods:
                    key = None if p == [EPS] else p[0]
                    groups.setdefault(key, []).append(p)
                target = next(((k, g) for k, g in groups.items() if k is not None and len(g) > 1), None)
                if not target:
                    break
                did_factor = True
                key, grp = target
                prefix = common_prefix(grp)
                new = self._new_name(head, used)
                rests = [p[len(prefix):] or [EPS] for p in grp]
                before = [rule_str(head, p) for p in prods]
                rebuilt, placed = [], False
                for p in prods:
                    if p in grp:
                        if not placed:
                            rebuilt.append(prefix + [new])
                            placed = True
                    else:
                        rebuilt.append(p)
                prods = rebuilt
                steps.append({
                    "non_terminal": head,
                    "status": "Factored",
                    "common_prefix": fmt(prefix),
                    "before": before,
                    "after": [rule_str(head, p) for p in prods] + [rule_str(new, r) for r in rests],
                    "explain": [
                        f"Productions {', '.join(rule_str(head, p) for p in grp)} share the prefix  {fmt(prefix)}  (α).",
                        f"Pull α out:  {head} → α {new}  and put the differing tails (β's) under {new}: "
                        + " | ".join(fmt(r) for r in rests) + ".",
                    ],
                })
                factor(new, rests, False)
            if not did_factor and original_nt:
                steps.append({
                    "non_terminal": head, "status": "No Common Prefix",
                    "common_prefix": "",
                    "before": [rule_str(head, p) for p in prods],
                    "after": [rule_str(head, p) for p in prods],
                    "explain": [f"No two productions of {head} begin with the same symbol."],
                })
            out[head] = prods

        for head, prods in list(grammar.items()):
            factor(head, prods, True)
        return steps, out

    # ------------------------------------------------------ FIRST and FOLLOW
    def _explain_first(self, A, p, first):
        if p == [EPS]:
            return f"{rule_str(A, p)} is an ε-production, so ε ∈ FIRST({A})."
        x = p[0]
        if x not in self.grammar:
            return f"{rule_str(A, p)} starts with terminal '{x}', so '{x}' ∈ FIRST({A})."
        parts = []
        for s in p:
            if s in self.grammar:
                parts.append(f"FIRST({s}) = {{{', '.join(sort_syms(first[s]))}}}")
                if EPS not in first[s]:
                    break
                parts.append(f"{s} is nullable, so look at the next symbol")
            else:
                parts.append(f"terminal '{s}'")
                break
        else:
            parts.append("every symbol is nullable, so ε is added")
        return f"{rule_str(A, p)}: " + "; ".join(parts) + "."

    def compute_first_follow_with_explanation(self, grammar):
        nts = list(grammar)
        first = {n: set() for n in nts}
        first_log, passno, changed = [], 0, True
        while changed:
            changed, passno = False, passno + 1
            for A, prods in grammar.items():
                for p in prods:
                    fs = first_of_seq(p, first, grammar)
                    new = fs - first[A]
                    if new:
                        reason = self._explain_first(A, p, first)
                        first[A] |= new
                        changed = True
                        first_log.append({"pass": passno, "non_terminal": A, "production": rule_str(A, p),
                                          "added": sort_syms(new), "reason": reason})

        # which productions contribute which symbol (final sets)
        first_contrib = {A: defaultdict(list) for A in nts}
        for A, prods in grammar.items():
            for p in prods:
                for x in first_of_seq(p, first, grammar):
                    first_contrib[A][x].append(rule_str(A, p))

        follow = {n: set() for n in nts}
        follow[self.start_symbol].add(END)
        follow_log = [{"pass": 0, "non_terminal": self.start_symbol, "rule": 1,
                       "production": "start symbol",
                       "reason": f"Rule 1: {self.start_symbol} is the start symbol, so $ ∈ FOLLOW({self.start_symbol}).",
                       "added": [END]}]
        passno, changed = 0, True
        while changed:
            changed, passno = False, passno + 1
            for A, prods in grammar.items():
                for p in prods:
                    for i, B in enumerate(p):
                        if B not in grammar:
                            continue
                        beta = p[i + 1:]
                        fb = first_of_seq(beta, first, grammar)
                        new = (fb - {EPS}) - follow[B]
                        if new:
                            follow[B] |= new
                            changed = True
                            follow_log.append({
                                "pass": passno, "non_terminal": B, "rule": 2, "production": rule_str(A, p),
                                "reason": f"Rule 2: in {rule_str(A, p)}, {B} is followed by "
                                          f"{fmt(beta)}; FIRST({fmt(beta)}) − {{ε}} = {{{', '.join(sort_syms(fb - {EPS}))}}}.",
                                "added": sort_syms(new)})
                        if EPS in fb:
                            new = follow[A] - follow[B]
                            if new:
                                follow[B] |= new
                                changed = True
                                why = (f"{B} is at the end of {rule_str(A, p)}" if not beta
                                       else f"what follows {B} ({fmt(beta)}) can vanish (ε)")
                                follow_log.append({
                                    "pass": passno, "non_terminal": B, "rule": 3, "production": rule_str(A, p),
                                    "reason": f"Rule 3: {why}, so FOLLOW({A}) = {{{', '.join(sort_syms(follow[A]))}}} ⊆ FOLLOW({B}).",
                                    "added": sort_syms(new)})

        follow_contrib = {A: defaultdict(list) for A in nts}
        follow_contrib[self.start_symbol][END].append("Rule 1: start symbol")
        for A, prods in grammar.items():
            for p in prods:
                for i, B in enumerate(p):
                    if B not in grammar:
                        continue
                    fb = first_of_seq(p[i + 1:], first, grammar)
                    for x in fb - {EPS}:
                        follow_contrib[B][x].append(f"Rule 2 via {rule_str(A, p)}")
                    if EPS in fb:
                        for x in follow[A]:
                            follow_contrib[B][x].append(f"Rule 3 via {rule_str(A, p)} (inherits FOLLOW({A}))")

        def pack(contrib, sets):
            return {A: [{"symbol": s, "sources": sorted(set(contrib[A][s]))} for s in sort_syms(sets[A])]
                    for A in nts}

        return (
            first_log, follow_log,
            {k: sort_syms(v) for k, v in first.items()},
            {k: sort_syms(v) for k, v in follow.items()},
            pack(first_contrib, first), pack(follow_contrib, follow),
        )

    # -------------------------------------------------------------- LL(1) table
    def build_ll1_table(self, grammar, first, follow):
        terms = list(self.terminal_order) + [END]
        table = {A: {t: [] for t in terms} for A in grammar}
        fsets = {k: set(v) for k, v in first.items()}

        def add(A, t, p, source):
            if t not in table[A]:
                table[A][t] = []
            if all(e["prod"] != p for e in table[A][t]):
                table[A][t].append({"prod": p, "source": source})

        for A, prods in grammar.items():
            for p in prods:
                fs = first_of_seq(p, fsets, grammar)
                for t in fs - {EPS}:
                    add(A, t, p, "FIRST")
                if EPS in fs:
                    for t in follow.get(A, []):
                        add(A, t, p, "FOLLOW")

        conflicts = []
        for A in grammar:
            for t in terms:
                cell = table[A][t]
                if len(cell) > 1:
                    sources = {e["source"] for e in cell}
                    if sources == {"FIRST"}:
                        kind, why = "FIRST/FIRST", "Several alternatives can start with the same terminal (common prefix or ambiguity). Try left factoring."
                    elif sources == {"FOLLOW"}:
                        kind, why = "FOLLOW/FOLLOW", "Several alternatives are nullable and share a FOLLOW symbol; the grammar is ambiguous."
                    else:
                        kind, why = "FIRST/FOLLOW", "A nullable alternative competes with another one on a symbol in FOLLOW. The grammar is not LL(1)."
                    conflicts.append({
                        "non_terminal": A, "terminal": t, "kind": kind, "why": why,
                        "productions": [rule_str(A, e["prod"]) for e in cell],
                    })
        return table, conflicts

    def serialise_table(self, table):
        return {A: {t: [{"rule": rule_str(A, e["prod"]), "prod": fmt(e["prod"]), "source": e["source"]}
                        for e in cell] for t, cell in row.items()} for A, row in table.items()}

    # ------------------------------------------------------------ tokenising
    def tokenize(self, s):
        """Split on whitespace; if a chunk is not a terminal try to split it into terminals
        ('id+id*id' -> id + id * id)."""
        s = (s or "").strip()
        if s in EPS_ALIASES or s == "":
            return [], None
        terms = sorted((t for t in self.terminal_order), key=len, reverse=True)
        memo = {}

        def seg(chunk, i):
            if i == len(chunk):
                return []
            if i in memo:
                return memo[i]
            res = None
            for t in terms:
                if chunk.startswith(t, i):
                    rest = seg(chunk, i + len(t))
                    if rest is not None:
                        res = [t] + rest
                        break
            memo[i] = res
            return res

        tokens, split = [], False
        for chunk in s.split():
            if chunk in self.terminals:
                tokens.append(chunk)
                continue
            memo.clear()
            parts = seg(chunk, 0)
            if parts:
                tokens.extend(parts)
                split = True
            else:
                tokens.append(chunk)
        note = "Input was split into tokens: " + " ".join(tokens) if split else None
        return tokens, note

    # ------------------------------------------------------------- parsing
    def trace_parser(self, tokens_in, grammar, table):
        tokens = list(tokens_in) + [END]
        stack = [END, self.start_symbol]
        idx, nid = 0, 0
        root = {"id": nid, "label": self.start_symbol, "type": "nt", "children": [], "step": 0}
        nid += 1
        stack_nodes = [None, root]
        trace, warnings = [], []

        def finish(ok, error):
            if not ok:
                for n in stack_nodes:
                    if n is not None:
                        n["pending"] = True
            return ok, trace, root, error, warnings

        while stack:
            if len(trace) >= MAX_TRACE_STEPS:
                err = {"index": idx, "token": tokens[idx], "expected": [], "kind": "limit",
                       "message": "Parser did not terminate (the grammar may still be left-recursive)."}
                return finish(False, err)
            top, cur = stack[-1], tokens[idx]
            step = len(trace) + 1
            entry = {"step": step, "stack": " ".join(stack), "input": " ".join(tokens[idx:]),
                     "action": "", "kind": "", "cell": None, "index": idx}

            if top not in grammar:                                   # terminal or $
                if top == cur:
                    if top == END:
                        entry.update(action="Accept: input fully consumed", kind="accept")
                        trace.append(entry)
                        return finish(True, None)
                    entry.update(action=f"Match '{top}'", kind="match")
                    stack_nodes[-1]["matched_step"] = step
                    stack.pop(); stack_nodes.pop()
                    idx += 1
                else:
                    shown = "end of input" if cur == END else f"'{cur}'"
                    msg = (f"Syntax error at token {idx + 1}: expected '{top}' but found {shown}."
                           if top != END else f"Syntax error at token {idx + 1}: expected end of input but found {shown}.")
                    entry.update(action=f"Error: expected '{top}', found '{cur}'", kind="error")
                    if stack_nodes[-1] is not None:
                        stack_nodes[-1]["error"] = True
                    trace.append(entry)
                    return finish(False, {"index": idx, "token": cur, "expected": [top],
                                          "kind": "mismatch", "message": msg})
            else:                                                    # non-terminal
                row = table.get(top, {})
                entry["cell"] = [top, cur]
                if cur not in row:
                    entry.update(action=f"Error: '{cur}' is not a symbol of this grammar", kind="error")
                    stack_nodes[-1]["error"] = True
                    trace.append(entry)
                    exp = sort_syms(t for t, c in row.items() if c)
                    return finish(False, {"index": idx, "token": cur, "expected": exp, "kind": "unknown",
                                          "message": f"Syntax error at token {idx + 1}: '{cur}' is not a terminal of the grammar."})
                cell = row[cur]
                if not cell:
                    exp = sort_syms(t for t, c in row.items() if c)
                    shown = "end of input" if cur == END else f"'{cur}'"
                    entry.update(action=f"Error: empty table entry M[{top}, {cur}]", kind="error")
                    stack_nodes[-1]["error"] = True
                    trace.append(entry)
                    return finish(False, {"index": idx, "token": cur, "expected": exp, "kind": "empty",
                                          "message": f"Syntax error at token {idx + 1}: found {shown}, expected one of {{{', '.join(exp)}}}."})
                if len(cell) > 1:
                    w = f"Conflict at M[{top}, {cur}]: using first alternative {rule_str(top, cell[0]['prod'])}."
                    if w not in warnings:
                        warnings.append(w)
                prod = cell[0]["prod"]
                entry.update(action=f"Apply {rule_str(top, prod)}" + (" (conflict: first alternative chosen)" if len(cell) > 1 else ""),
                             kind="expand")
                stack.pop()
                node = stack_nodes.pop()
                if prod == [EPS]:
                    node["children"] = [{"id": nid, "label": EPS, "type": "eps", "children": [], "step": step,
                                         "matched_step": step}]
                    nid += 1
                else:
                    kids = []
                    for sym in prod:
                        kids.append({"id": nid, "label": sym, "type": "nt" if sym in grammar else "t",
                                     "children": [], "step": step})
                        nid += 1
                    node["children"] = kids
                    for sym, kid in zip(reversed(prod), reversed(kids)):
                        stack.append(sym)
                        stack_nodes.append(kid)
            trace.append(entry)
        return finish(False, {"index": idx, "token": END, "expected": [], "kind": "limit",
                              "message": "Parsing ended unexpectedly."})

    # ------------------------------------------------------------ ambiguity
    def detect_ambiguity(self, max_terms=5, node_cap=40000, max_depth=30):
        """Bounded probe on the ORIGINAL grammar: count distinct leftmost derivations of
        every short terminal string. >1 means the grammar is ambiguous (a proof);
        0 found is only evidence, not a proof."""
        nts = self.grammar
        frontier = {(self.start_symbol,): 1}
        done = defaultdict(int)
        nodes, truncated = 0, False
        max_len = 2 * max_terms + 2
        for _ in range(max_depth):
            nxt = defaultdict(int)
            for form, cnt in frontier.items():
                pos = next((i for i, s in enumerate(form) if s in nts), None)
                if pos is None:
                    done[form] += cnt
                    continue
                for p in nts[form[pos]]:
                    new = form[:pos] + (() if p == [EPS] else tuple(p)) + form[pos + 1:]
                    if len(new) > max_len or sum(1 for s in new if s not in nts) > max_terms:
                        continue
                    nxt[new] += cnt
                    nodes += 1
            frontier = nxt
            if not frontier:
                break
            if nodes > node_cap:
                truncated = True
                break
        else:
            truncated = True
        for form, cnt in frontier.items():
            if all(s not in nts for s in form):
                done[form] += cnt
        amb = sorted(((f, c) for f, c in done.items() if c > 1), key=lambda fc: (len(fc[0]), fc[0]))
        if amb:
            f, c = amb[0]
            text = " ".join(f) or "ε"
            return {"ambiguous": True, "example": text, "derivations": c,
                    "note": f"'{text}' has {c} different leftmost derivations, so the grammar is ambiguous."}
        return {"ambiguous": False, "example": None, "derivations": 0,
                "note": f"No string of up to {max_terms} terminals has two derivations"
                        + (" (search was cut off)" if truncated else "")
                        + ". This is a bounded check, not a proof."}

    # ------------------------------------------------------ practice support
    def _min_costs(self):
        INF = float("inf")
        cost = {A: INF for A in self.grammar}
        changed = True
        while changed:
            changed = False
            for A, prods in self.grammar.items():
                for p in prods:
                    c = 1 + sum(cost[s] for s in p if s in self.grammar)
                    if c < cost[A]:
                        cost[A], changed = c, True
        return cost

    def _derive(self, A, depth, rng, cost, budget):
        INF = float("inf")
        prods = [p for p in self.grammar[A] if 1 + sum(cost[s] for s in p if s in self.grammar) < INF]
        if not prods:
            return []
        pc = lambda p: 1 + sum(cost[s] for s in p if s in self.grammar)
        if depth <= 0 or budget[0] <= 0:
            best = min(pc(p) for p in prods)
            p = rng.choice([q for q in prods if pc(q) == best])
        else:
            p = rng.choice(prods)
        budget[0] -= 1
        out = []
        for s in p:
            if s == EPS:
                continue
            out.extend(self._derive(s, depth - 1, rng, cost, budget) if s in self.grammar else [s])
        return out

    def random_valid_tokens(self, rng, max_tokens=14):
        cost = self._min_costs()
        if cost[self.start_symbol] == float("inf"):
            return []
        for _ in range(30):
            toks = self._derive(self.start_symbol, rng.randint(2, 7), rng, cost, [40])
            if len(toks) <= max_tokens:
                return toks
        return toks

    def mutate(self, toks, rng):
        toks = list(toks)
        terms = self.terminal_order or ["x"]
        ops = ["insert", "replace", "swap", "dup", "truncate", "delete"]
        for _ in range(10):
            t, op = list(toks), rng.choice(ops)
            if op == "insert" or not t:
                t.insert(rng.randint(0, len(t)), rng.choice(terms))
            elif op == "delete":
                t.pop(rng.randrange(len(t)))
            elif op == "replace":
                t[rng.randrange(len(t))] = rng.choice(terms)
            elif op == "swap" and len(t) > 1:
                i = rng.randrange(len(t) - 1)
                t[i], t[i + 1] = t[i + 1], t[i]
            elif op == "dup":
                i = rng.randrange(len(t))
                t.insert(i, t[i])
            elif op == "truncate" and len(t) > 1:
                t = t[: rng.randint(1, len(t) - 1)]
            if t != toks:
                return t
        return toks + [rng.choice(terms)]

    def _pipeline(self):
        _, lr_g = self.eliminate_left_recursion()
        _, final = self.left_factoring(lr_g)
        first_log, follow_log, first, follow, fc, flc = self.compute_first_follow_with_explanation(final)
        table, conflicts = self.build_ll1_table(final, first, follow)
        return final, first, follow, table, conflicts

    def accepts(self, text, pipeline=None):
        final, first, follow, table, conflicts = pipeline or self._pipeline()
        toks, _ = self.tokenize(text)
        ok, trace, tree, err, warn = self.trace_parser(toks, final, table)
        return ok, trace, err

    def generate_practice_questions(self, count=6, seed=None):
        rng = random.Random(seed)
        pipe = self._pipeline()
        want_ok = (count + 1) // 2
        accepted, rejected, seen = [], [], set()

        def consider(toks):
            s = " ".join(toks)
            if s in seen:
                return
            seen.add(s)
            ok, _, _ = self.accepts(s, pipe)
            (accepted if ok else rejected).append(s)

        consider([])  # the empty string is always an interesting epsilon edge case
        for _ in range(300):
            if len(accepted) >= want_ok + 2 and len(rejected) >= count - want_ok + 2:
                break
            valid = self.random_valid_tokens(rng)
            consider(valid)
            consider(self.mutate(valid, rng))
        rng.shuffle(accepted)
        rng.shuffle(rejected)
        # keep ε only when it adds variety, and keep the mix balanced
        picks = accepted[:want_ok] + rejected[: count - want_ok]
        rest = [s for s in accepted[want_ok:] + rejected[count - want_ok:] if s not in picks]
        picks += rest[: count - len(picks)]
        rng.shuffle(picks)
        return [{"id": i + 1, "test_string": s, "display": s if s else "ε (empty string)"}
                for i, s in enumerate(picks[:count])]

    def check_prediction(self, text, prediction):
        ok, trace, err = self.accepts(text)
        if ok:
            detail = f"The parser accepts this string in {len(trace)} steps; the parse tree is complete."
        else:
            detail = err["message"]
        return {"accepted": ok, "correct": bool(prediction) == ok, "detail": detail, "error": err,
                "steps": len(trace)}

    def suggest_samples(self, pipeline=None):
        pipe = pipeline or self._pipeline()
        rng = random.Random(7)
        samples, seen = [], set()

        def add(kind, toks):
            s = " ".join(toks)
            if (s, kind) in seen or len(samples) > 8 or (s == "" and kind != "epsilon"):
                return
            seen.add((s, kind))
            ok, _, _ = self.accepts(s, pipe)
            samples.append({"kind": "epsilon" if kind == "epsilon" else ("valid" if ok else "invalid"),
                            "text": s, "verdict": ok})

        valids = sorted({tuple(self.random_valid_tokens(rng)) for _ in range(12)}, key=lambda t: (len(t), t))
        valids = [list(v) for v in valids if v][:3]
        for v in valids:
            add("valid", v)
        if valids:
            for k in range(2):
                add("invalid", self.mutate(valids[min(k, len(valids) - 1)], rng))
        add("epsilon", [])
        return samples

    # ---------------------------------------------------------- everything
    def process_all(self, test_string):
        lr_steps, lr_g = self.eliminate_left_recursion()
        lf_steps, final = self.left_factoring(lr_g)
        first_log, follow_log, first, follow, first_contrib, follow_contrib = \
            self.compute_first_follow_with_explanation(final)
        table, conflicts = self.build_ll1_table(final, first, follow)
        tokens, note = self.tokenize(test_string)
        ok, trace, tree, error, warnings = self.trace_parser(tokens, final, table)
        pipe = (final, first, follow, table, conflicts)
        return {
            "start_symbol": self.start_symbol,
            "non_terminals": list(final.keys()),
            "terminals": list(self.terminal_order) + [END],
            "original_grammar": {k: [fmt(p) for p in v] for k, v in self.grammar.items()},
            "left_recursion_steps": lr_steps,
            "left_factoring_steps": lf_steps,
            "final_grammar": {k: [fmt(p) for p in v] for k, v in final.items()},
            "first_log": first_log,
            "follow_log": follow_log,
            "first_sets": first,
            "follow_sets": follow,
            "first_contrib": first_contrib,
            "follow_contrib": follow_contrib,
            "ll1_table": self.serialise_table(table),
            "conflicts": conflicts,
            "is_ll1": not conflicts,
            "ambiguity": self.detect_ambiguity(),
            "tokens": tokens,
            "token_note": note,
            "parse_success": ok,
            "parse_trace": trace,
            "parse_tree": tree,
            "parse_warnings": warnings,
            "error": error,
            "error_msg": error["message"] if error else None,
            "samples": self.suggest_samples(pipe),
        }
