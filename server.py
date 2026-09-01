from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3
import datetime
import os

app = Flask(__name__)
CORS(app)

DB_FILE = 'rfid_logs.db'

HTML = """
<!DOCTYPE html>
<html>
<head><title>RFID Контроль доступа</title></head>
<body>
<h1>🏢 RFID Контроль доступа</h1>
<p>Сервер работает!</p>
<p>👤 Людей внутри: <strong id="count">0</strong></p>
<script>
fetch('/api/public-data')
  .then(r => r.json())
  .then(d => document.getElementById('count').textContent = d.inside_count);
</script>
</body>
</html>
"""

def init_db():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE users (uid TEXT PRIMARY KEY, name TEXT, surname TEXT, is_inside INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, uid TEXT NOT NULL, timestamp TEXT NOT NULL)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return render_template_string(HTML)

@app.route('/rfid', methods=['GET'])
def handle_rfid():
    reader = request.args.get('reader')
    uid = request.args.get('uid')
    if not reader or not uid:
        return jsonify({"error": "Missing parameters"}), 400

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute("SELECT name, surname, is_inside FROM users WHERE uid = ?", (uid,))
    user = c.fetchone()
    
    if not user:
        c.execute("INSERT INTO users (uid, name, surname, is_inside) VALUES (?, 'User', 'User', 0)", (uid,))
        c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('register', ?, ?)", (uid, now))
        conn.commit()
        c.execute("SELECT name, surname, is_inside FROM users WHERE uid = ?", (uid,))
        user = c.fetchone()

    name, surname, is_inside = user

    if reader == "1":
        if is_inside:
            action = "blocked_enter"
            message = "already_inside"
        else:
            action = "enter"
            c.execute("UPDATE users SET is_inside = 1 WHERE uid = ?", (uid,))
            message = "enter_ok"
    elif reader == "2":
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
    return jsonify({"status": "ok", "message": message, "name": name, "surname": surname})

@app.route('/api/public-data', methods=['GET'])
def public_data():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE is_inside = 1")
    inside_count = c.fetchone()[0]
    conn.close()
    return jsonify({"inside_count": inside_count})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
