from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

CLICK_COUNTER_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Click Counter</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      color: #fff;
    }

    .container {
      text-align: center;
      padding: 3rem 4rem;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 24px;
      backdrop-filter: blur(12px);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }

    h1 {
      font-size: 1.4rem;
      font-weight: 500;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      opacity: 0.7;
      margin-bottom: 1.5rem;
    }

    #count {
      font-size: 6rem;
      font-weight: 700;
      line-height: 1;
      margin-bottom: 2rem;
      transition: transform 0.1s ease;
    }

    #count.bump {
      transform: scale(1.15);
    }

    .buttons {
      display: flex;
      gap: 1rem;
      justify-content: center;
    }

    button {
      padding: 0.75rem 2rem;
      font-size: 1.1rem;
      font-weight: 600;
      border: none;
      border-radius: 12px;
      cursor: pointer;
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }

    button:active {
      transform: scale(0.95);
    }

    .btn-click {
      background: linear-gradient(135deg, #667eea, #764ba2);
      color: #fff;
      box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
    }

    .btn-click:hover {
      box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
    }

    .btn-reset {
      background: rgba(255, 255, 255, 0.1);
      color: rgba(255, 255, 255, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.15);
    }

    .btn-reset:hover {
      background: rgba(255, 255, 255, 0.15);
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Click Counter</h1>
    <div id="count">0</div>
    <div class="buttons">
      <button class="btn-click" onclick="increment()">Click me</button>
      <button class="btn-reset" onclick="resetCount()">Reset</button>
    </div>
  </div>

  <script>
    let count = 0;
    const display = document.getElementById('count');

    function increment() {
      count++;
      display.textContent = count;
      display.classList.add('bump');
      setTimeout(() => display.classList.remove('bump'), 100);
    }

    function resetCount() {
      count = 0;
      display.textContent = count;
    }
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return jsonify({"status": "ok", "message": "Dispatch Companion API"})


@app.route("/click-counter")
def click_counter():
    return render_template_string(CLICK_COUNTER_PAGE)


@app.route("/health")
def health():
    return jsonify({"healthy": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
