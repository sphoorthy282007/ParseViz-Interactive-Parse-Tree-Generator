from flask import Flask, render_template, request, jsonify

from parser_engine import ParseVizEngine, GrammarError

app = Flask(__name__)
app.json.sort_keys = False  # keep grammar / table order exactly as the engine produced it


def _engine_from_request():
    data = request.get_json(silent=True) or {}
    return ParseVizEngine(data.get("grammar", "")), data


@app.errorhandler(GrammarError)
def grammar_error(err):
    return jsonify({"error": str(err)}), 400


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    engine, data = _engine_from_request()
    return jsonify(engine.process_all(data.get("test_string", "")))


@app.route("/api/practice", methods=["POST"])
def practice_quiz():
    """Generate a fresh round of test strings (verdicts are NOT sent to the browser)."""
    engine, data = _engine_from_request()
    try:
        count = max(3, min(15, int(data.get("count", 6))))
    except (TypeError, ValueError):
        count = 6
    return jsonify({"questions": engine.generate_practice_questions(count)})


@app.route("/api/practice/check", methods=["POST"])
def practice_check():
    """Run the real parser on a string and compare with the student's prediction."""
    engine, data = _engine_from_request()
    return jsonify(engine.check_prediction(data.get("test_string", ""), bool(data.get("prediction"))))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
