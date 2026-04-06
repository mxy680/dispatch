from flask import Flask, render_template, jsonify

app = Flask(__name__)

click_count = 0


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/click", methods=["POST"])
def click():
    global click_count
    click_count += 1
    return jsonify(count=click_count)


@app.route("/api/count")
def count():
    return jsonify(count=click_count)


@app.route("/api/reset", methods=["POST"])
def reset():
    global click_count
    click_count = 0
    return jsonify(count=click_count)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
