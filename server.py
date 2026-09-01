from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3
import datetime
import os

app = Flask(__name__)
CORS(app)

DB_FILE = 'rfid_logs.db'

# ==================== HTML САЙТА ====================
HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>RFID Контроль доступа</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Segoe UI', Arial, sans-serif;
  background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460);
  color: white;
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
}
.container { max-width: 500px; width: 100%; text-align: center; }
h1 {
  font-size: 2.5em;
  background: linear-gradient(135deg, #2ecc71, #f5a623);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 10px;
}
.card {
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(10px);
  border-radius: 15px;
  padding: 30px;
  border: 1px solid rgba(255,255,255,0.1);
  margin-top: 20px;
}
.number {
  font-size: 4em;
  font-weight: bold;
  background: linear-gradient(135deg, #2ecc71, #f5a623);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.label { color: #aaa; margin-top: 10px; font-size: 1.1em; }
.footer { margin-top: 30px; color: #555; font-size: 0.8em; }
</style>
</head>
<body>
<div class="container">
  <h1>🏢 RFID Контроль доступа</h1>
  <div class="card">
    <div class="number" id="count">0</div>
    <div class="label">👤 Людей внутри</div>
  </div>
  <div class="footer">Система работает</div>
</div>
<script>
function update() {
  fetch('/api/public-data')
    .then(r => r.json())
    .then(d => document.getElementById('count').textContent = d.inside_count)
    .catch(() => {});
}
setInterval(update, 2000);
update();
</script>
</body>
</html>
"""

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE users (
        uid TEXT PRIMARY KEY,
        name TEXT,
        surname TEXT,
        is_inside INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT NOT NULL,
        uid TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )''')
    conn.commit()
    conn.close()

init_db()

# ==================== API ====================
@app.route('/')
def home():
    return render_template_string(HTML)

@app.route('/rfid', methods=['GET'])
def handle_rfid():
    reader = request.args.get('reader')
    uid = request.args.get('uid')
    
    if not reader or not uid:
        return jsonify({"error": "Missing parameters"}), 400

    print(f"📥 reader={reader}, uid={uid}")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Проверяем, есть ли пользователь
    c.execute("SELECT name, surname, is_inside FROM users WHERE uid = ?", (uid,))
    user = c.fetchone()
    
    if not user:
        # Автоматическая регистрация
        c.execute("INSERT INTO users (uid, name, surname, is_inside) VALUES (?, 'User', 'User', 0)", (uid,))
        c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('register', ?, ?)", (uid, now))
        conn.commit()
        c.execute("SELECT name, surname, is_inside FROM users WHERE uid = ?", (uid,))
        user = c.fetchone()

    name, surname, is_inside = user
    message = ""

    if reader == "1":  # ВХОД
        if is_inside:
            action = "blocked_enter"
            message = "already_inside"
        else:
            action = "enter"
            c.execute("UPDATE users SET is_inside = 1 WHERE uid = ?", (uid,))
            message = "enter_ok"

    elif reader == "2":  # ВЫХОД
        if not is_inside:
            action = "blocked_exit"
            message = "already_outside"
        else:
            action = "exit"
            c.execute("UPDATE users SET is_inside = 0 WHERE uid = ?", (uid,))
            message = "exit_ok"
    else:
        conn.close()
        return jsonify({"error": "Invalid reader"}), 400

    c.execute("INSERT INTO events (action, uid, timestamp) VALUES (?, ?, ?)", (action, uid, now))
    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "ok",
        "message": message,
        "name": name,
        "surname": surname
    })

@app.route('/api/public-data', methods=['GET'])
def public_data():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE is_inside = 1")
    inside_count = c.fetchone()[0]
    conn.close()
    return jsonify({"inside_count": inside_count})

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
