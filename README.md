# ParseViz — Interactive Parse Tree Generator (LL(1) Studio)

PS-03, Unit II (Top-Down Parsing): a practice studio that shows grammar transformation,
FIRST/FOLLOW, the LL(1) table, a parsing trace and an animated parse tree.

## Run

```bash
pip install -r requirements.txt
python app.py            # open http://127.0.0.1:5000
python -m unittest discover -s tests    # engine tests
```

The page loads Bootstrap, D3 and fonts from CDNs, so it needs internet access in the browser.

## Project layout

```
app.py               Flask routes (/api/analyze, /api/practice, /api/practice/check)
parser_engine.py     All algorithms (no Flask dependency)
templates/index.html Front-end (Bootstrap + D3)
tests/test_engine.py Unit tests for the edge cases listed below
```

## Features (what is new compared with the first version)

1. **Left recursion** — immediate recursion with α/β shown per step; `A → A a | ε` handled
   correctly (gives `A → A'`); indirect recursion removed by substitution first (Paull);
   warning when a non-terminal has no non-recursive alternative.
2. **Left factoring** — longest common prefix, repeated until no prefix remains
   (nested factoring), with before/after rules for every step.
3. **FIRST / FOLLOW** — every set addition is logged with the pass, the production and the rule
   that caused it; final table shows the contributing productions on hover and in a
   collapsible list.
4. **LL(1) table** — cells coloured as production / conflict / empty (error). Conflicts are
   de-duplicated and classified as FIRST/FIRST, FIRST/FOLLOW or FOLLOW/FOLLOW, with a hint.
   Multiple conflicts are all reported. The cell used by the selected trace step is highlighted.
5. **Parsing trace** — stack, remaining input and action for every step; failure shows the
   token strip with the error token marked, its position and the expected symbols. On a conflict
   the parser takes the first alternative and warns.
6. **Parse tree** — animated D3 tree driven by the trace: play/pause, step buttons and a slider.
   Terminals turn green when matched; ε leaves are dashed. For rejected strings the partial tree
   is shown with the failing node in red.
7. **Test string helpers** — generated valid / invalid / empty-string samples as one-click chips;
   un-spaced input such as `id+id*id` is split into tokens automatically.
8. **Ambiguity probe** — bounded search for a string with two leftmost derivations (shown in the
   summary strip). A hit proves ambiguity; no hit is only evidence.
9. **Practice mode (bonus)** — generates new strings from the current grammar (valid, corrupted,
   empty). The student predicts accept/reject, the server runs the real parser, and the score,
   streak and a review table are shown. “See trace & tree” opens any question in the studio.
10. Seven built-in example grammars (left recursion, ε, common prefix, dangling else, two
    conflicts, indirect recursion, ambiguity), dark/light theme, input validation with clear errors.

## Grammar syntax

* One rule per line: `A -> x B | y` (also `→` and `::=`). Alternatives separated by `|`.
* Separate every symbol with a space.
* Epsilon: `ε`, `e`, `eps`, `epsilon`, `#`, `λ` (alone in an alternative) or an empty alternative.
  Because of this, a terminal literally named `e` cannot be used.
* Symbols on a left-hand side are non-terminals; everything else is a terminal. `//` starts a comment line.

## Limits

* Practice verdicts are the LL(1) parser's verdicts; for a grammar that is not LL(1) the first
  alternative of a conflicting cell is used.
* Indirect-recursion removal assumes no ε-productions among the substituted non-terminals (Paull's precondition).
* The ambiguity probe only looks at strings of up to 5 terminals.

## How to run it (Windows)
Install Python 3.10 or newer first, then open Command Prompt in the project folder.
1. Go to the folder: cd C:\Users\Dell\Desktop\parseviz
2. Install the requirements once: pip install -r requirements.txt
3. Start the server: python app.py
4. Open http://127.0.0.1:5000 in a browser (the page loads Bootstrap and D3 from a CDN, so it needs internet).
5. Stop the server with Ctrl+C.
To use it: type or pick a grammar, enter a test string (or leave it empty for the empty string), click Analyze & Run, then walk through tabs 1 to 5. Open tab 6 to practise.
To run the tests: python -m unittest discover -s tests

## Deploy (Render, free tier)

1. Push this folder to a GitHub repository (`app.py`, `Procfile` and `requirements.txt` must be at the repo root).
2. On https://render.com choose **New → Web Service**, connect the repo.
3. Settings: Runtime **Python 3**, Build command `pip install -r requirements.txt`, Start command `gunicorn app:app`.
4. Click **Create Web Service**. After the build you get a public `https://<name>.onrender.com` link.

The same `Procfile` works on Railway and Heroku. On PythonAnywhere, create a Flask web app and point its WSGI file at `from app import app as application`.
