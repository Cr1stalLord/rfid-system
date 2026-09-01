from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3
import datetime
import os

app = Flask(__name__)
CORS(app)

DB_FILE = 'rfid_logs.db'

# ==================== ПУБЛИЧНЫЙ САЙТ ====================
PUBLIC_HTML = """
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

# ==================== АДМИН-ПАНЕЛЬ ====================
ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>RFID Админ-панель</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Segoe UI', Arial, sans-serif;
  background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460);
  color: white;
  min-height: 100vh;
  padding: 20px;
}
.container { max-width: 1000px; margin: 0 auto; }
h1 { text-align: center; margin-bottom: 30px; color: #e94560; }
.card {
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(10px);
  border-radius: 15px;
  padding: 20px;
  border: 1px solid rgba(255,255,255,0.1);
  margin-bottom: 20px;
}
table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 10px; color: #aaa; border-bottom: 1px solid #333; }
td { padding: 10px; border-bottom: 1px solid #222; }
.btn {
  background: #e94560;
  border: none;
  color: white;
  padding: 8px 20px;
  border-radius: 8px;
  cursor: pointer;
}
.btn-green { background: #2ecc71; }
.btn-red { background: #e74c3c; }
.led { display: inline-block; width: 16px; height: 16px; border-radius: 50%; margin-right: 10px; }
.led-green { background: #2ecc71; }
.led-red { background: #e74c3c; }
</style>
</head>
<body>
<div class="container">
  <h1>🔐 RFID Админ-панель</h1>
  
  <div class="card">
    <h2>📊 Статистика</h2>
    <p>👤 Людей внутри: <strong id="count">0</strong></p>
    <p>📋 Всего событий: <strong id="events">0</strong></p>
  </div>

  <div class="card">
    <h2>📋 Пользователи</h2>
    <div id="usersList">Загрузка...</div>
  </div>

  <div class="card">
    <h2>📝 Управление регистрацией</h2>
    <p>
      <span class="led" id="regLed"></span>
      <span id="regStatus">Закрыта</span>
    </p>
    <button class="btn" id="toggleRegBtn">Открыть регистрацию</button>
  </div>
</div>

<script>
const API_URL = window.location.origin;

async function loadData() {
  const resp = await fetch(API_URL + '/api/get-users');
  const data = await resp.json();
  
  document.getElementById('count').textContent = data.users.filter(u => u.is_inside).length;
  document.getElementById('events').textContent = data.events.length;

  const list = document.getElementById('usersList');
  if (data.users.length === 0) {
    list.innerHTML = '<p style="color:#aaa;">Нет зарегистрированных пользователей</p>';
  } else {
    let html = '<table><tr><th>Имя</th><th>UID</th><th>Статус</th></tr>';
    data.users.forEach(u => {
      const status = u.is_inside ? 'Внутри' : 'Снаружи';
      const color = u.is_inside ? '#2ecc71' : '#f1c40f';
      html += `<tr><td>${u.name} ${u.surname}</td><td>${u.uid}</td><td style="color:${color}">${status}</td></tr>`;
    });
    html += '</table>';
    list.innerHTML = html;
  }

  const sr = await fetch(API_URL + '/api/registration-status');
  const sd = await sr.json();
  const led = document.getElementById('regLed');
  const text = document.getElementById('regStatus');
  const btn = document.getElementById('toggleRegBtn');
  if (sd.open) {
    led.className = 'led led-green';
    text.textContent = 'Открыта';
    btn.textContent = 'Закрыть регистрацию';
  } else {
    led.className = 'led led-red';
    text.textContent = 'Закрыта';
    btn.textContent = 'Открыть регистрацию';
  }
}

document.getElementById('toggleRegBtn').addEventListener('click', async () => {
  await fetch(API_URL + '/toggle-registration', { method: 'POST' });
  loadData();
});

setInterval(loadData, 2000);
loadData();
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

registration_open = False

# ==================== API ====================
@app.route('/')
def home():
    return render_template_string(PUBLIC_HTML)

@app.route('/admin')
def admin():
    return render_template_string(ADMIN_HTML)

@app.route('/toggle-registration', methods=['POST'])
def toggle_registration():
    global registration_open
    registration_open = not registration_open
    return jsonify({"open": registration_open})

@app.route('/api/registration-status', methods=['GET'])
def registration_status():
    return jsonify({"open": registration_open})

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
        else:
            action = "enter"
            c.execute("UPDATE users SET is_inside = 1 WHERE uid = ?", (uid,))
    elif reader == "2":
        if not is_inside:
            action = "blocked_exit"
        else:
            action = "exit"
            c.execute("UPDATE users SET is_inside = 0 WHERE uid = ?", (uid,))
    else:
        conn.close()
        return jsonify({"error": "Invalid reader"}), 400

    c.execute("INSERT INTO events (action, uid, timestamp) VALUES (?, ?, ?)", (action, uid, now))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/get-users', methods=['GET'])
def get_users():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT action, uid, timestamp FROM events ORDER BY id DESC LIMIT 50")
    events = c.fetchall()
    c.execute("SELECT uid, name, surname, is_inside FROM users")
    users = [{"uid": row[0], "name": row[1], "surname": row[2], "is_inside": row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify({"events": events, "users": users})

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
