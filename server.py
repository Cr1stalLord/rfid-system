from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3
import datetime
import os

app = Flask(__name__)
CORS(app)

DB_FILE = 'rfid_logs.db'

# ==================== КРАСИВЫЙ ПУБЛИЧНЫЙ САЙТ ====================
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
.container { max-width: 600px; width: 100%; text-align: center; }
.header h1 {
  font-size: 2.5em;
  background: linear-gradient(135deg, #2ecc71, #f5a623);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 10px;
}
.stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin: 30px 0;
}
.stat-card {
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(10px);
  padding: 20px;
  border-radius: 15px;
  border: 1px solid rgba(255,255,255,0.1);
}
.stat-card .number {
  font-size: 3em;
  font-weight: bold;
  background: linear-gradient(135deg, #2ecc71, #f5a623);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.stat-card .label { color: #aaa; margin-top: 5px; font-size: 0.9em; }
.card {
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(10px);
  border-radius: 15px;
  padding: 25px;
  border: 1px solid rgba(255,255,255,0.1);
  margin-top: 20px;
}
.card h2 { color: #f5a623; margin-bottom: 15px; font-size: 1.2em; }
.footer { margin-top: 30px; color: #555; font-size: 0.8em; }
</style>
</head>
<body>
<div class="container">
  <div class="header"><h1>🏢 RFID Контроль доступа</h1><p style="color:#aaa;">Текущий статус системы</p></div>
  <div class="stats">
    <div class="stat-card">
      <div class="number" id="currentPeople">0</div>
      <div class="label">👤 Людей внутри</div>
    </div>
    <div class="stat-card">
      <div class="number" id="lastEventTime">--:--</div>
      <div class="label">🕒 Последнее событие</div>
    </div>
  </div>
  <div class="card">
    <h2>📝 Регистрация</h2>
    <div id="regStatus" style="color:#aaa;">🔒 Регистрация закрыта</div>
  </div>
  <div class="footer"><span>Система работает</span></div>
</div>
<script>
async function loadData() {
  try {
    const resp = await fetch('/api/public-data');
    const data = await resp.json();
    document.getElementById('currentPeople').textContent = data.inside_count || 0;
    document.getElementById('lastEventTime').textContent = data.last_time ? data.last_time.substring(11, 16) : '--:--';
    const status = document.getElementById('regStatus');
    if (data.registration_open) {
      status.innerHTML = '✅ Регистрация <span style="color:#2ecc71;">ОТКРЫТА</span>';
    } else {
      status.innerHTML = '🔒 Регистрация <span style="color:#e74c3c;">ЗАКРЫТА</span>';
    }
  } catch (e) { console.error(e); }
}
setInterval(loadData, 2000);
loadData();
</script>
</body>
</html>
"""

# ==================== КРАСИВАЯ АДМИН-ПАНЕЛЬ ====================
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
.container { max-width: 1200px; margin: 0 auto; }
.header { text-align: center; padding: 30px 0; border-bottom: 2px solid rgba(255,255,255,0.1); margin-bottom: 30px; }
.header h1 {
  font-size: 2.5em;
  background: linear-gradient(135deg, #e94560, #f5a623);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}
.stat-card {
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(10px);
  padding: 20px;
  border-radius: 15px;
  text-align: center;
  border: 1px solid rgba(255,255,255,0.1);
}
.stat-card .number {
  font-size: 2.5em;
  font-weight: bold;
  background: linear-gradient(135deg, #e94560, #f5a623);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.stat-card .label { color: #aaa; margin-top: 5px; font-size: 0.9em; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }
@media (max-width: 768px) { .grid-2 { grid-template-columns: 1fr; } }
.card {
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(10px);
  border-radius: 15px;
  padding: 25px;
  border: 1px solid rgba(255,255,255,0.1);
}
.card h2 { margin-bottom: 20px; font-size: 1.3em; color: #e94560; }
table { width: 100%; border-collapse: collapse; margin-top: 10px; }
th { text-align: left; padding: 12px; border-bottom: 2px solid rgba(255,255,255,0.1); color: #aaa; font-weight: 400; font-size: 0.9em; }
td { padding: 12px; border-bottom: 1px solid rgba(255,255,255,0.05); }
.status-enter { color: #2ecc71; }
.status-exit { color: #f1c40f; }
.status-blocked { color: #e74c3c; }
.status-register { color: #3498db; }
.btn {
  background: #e94560;
  border: none;
  color: white;
  padding: 10px 25px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1em;
  transition: 0.3s;
}
.btn:hover { opacity: 0.8; }
.btn-green { background: #2ecc71; }
.btn-danger { background: #e74c3c; padding: 5px 12px; font-size: 0.8em; }
.reg-block {
  margin-top: 20px;
  padding: 20px;
  background: rgba(255,255,255,0.03);
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.1);
}
.reg-block .indicator { display: flex; align-items: center; gap: 15px; margin-bottom: 15px; }
.led { width: 20px; height: 20px; border-radius: 50%; display: inline-block; transition: 0.3s; }
.led-green { background: #2ecc71; box-shadow: 0 0 15px #2ecc71; }
.led-red { background: #e74c3c; box-shadow: 0 0 15px #e74c3c; }
</style>
</head>
<body>
<div class="container">
  <div class="header"><h1>🔐 RFID Админ-панель</h1></div>
  <div class="stats">
    <div class="stat-card"><div class="number" id="totalEvents">0</div><div class="label">📊 Всего событий</div></div>
    <div class="stat-card" style="border:1px solid #2ecc71;"><div class="number" id="currentPeople">0</div><div class="label">👤 Сейчас внутри</div></div>
    <div class="stat-card"><div class="number" id="inMatch">0</div><div class="label">✅ Входов</div></div>
    <div class="stat-card"><div class="number" id="outCount">0</div><div class="label">🚪 Выходов</div></div>
    <div class="stat-card"><div class="number" id="lastEventTime">--:--</div><div class="label">🕒 Последнее событие</div></div>
  </div>
  <div class="grid-2">
    <div>
      <div class="card">
        <h2>📋 Лента событий</h2>
        <div style="max-height:400px;overflow-y:auto;">
          <table><thead><tr><th>Действие</th><th>Карта</th><th>Время</th></tr></thead><tbody id="eventsList"></tbody></table>
        </div>
      </div>
    </div>
    <div>
      <div class="card">
        <h2>👤 Управление</h2>
        <div class="reg-block">
          <div class="indicator">
            <span>Статус регистрации:</span>
            <span class="led" id="regLed"></span>
            <span id="regStatusText">Закрыта</span>
          </div>
          <button class="btn" id="toggleRegBtn">Открыть регистрацию</button>
        </div>
      </div>
      <div class="card" style="margin-top:20px;">
        <h2>📋 Пользователи</h2>
        <div style="max-height:300px;overflow-y:auto;">
          <table><thead><tr><th>Имя</th><th>UID</th><th>Статус</th></tr></thead><tbody id="usersList"></tbody></table>
        </div>
      </div>
    </div>
  </div>
</div>
<script>
const API_URL = window.location.origin;
let regOpen = false;

function updateRegUI() {
  const led = document.getElementById('regLed'), text = document.getElementById('regStatusText');
  const btn = document.getElementById('toggleRegBtn');
  if (regOpen) {
    led.className = 'led led-green'; text.textContent = 'Открыта';
    btn.textContent = 'Закрыть регистрацию';
  } else {
    led.className = 'led led-red'; text.textContent = 'Закрыта';
    btn.textContent = 'Открыть регистрацию';
  }
}

document.getElementById('toggleRegBtn').addEventListener('click', async () => {
  const resp = await fetch(API_URL + '/toggle-registration', { method: 'POST' });
  const data = await resp.json();
  regOpen = data.open; updateRegUI();
});

async function loadData() {
  const resp = await fetch(API_URL + '/api/get-users');
  const data = await resp.json();
  const list = document.getElementById('eventsList');
  list.innerHTML = '';
  let total=0, count1=0, count2=0, inside=0, last='--:--';
  if (data.events && data.events.length > 0) {
    total = data.events.length; last = data.events[0][2].substring(11,16);
    data.events.forEach(ev => {
      let a=ev[0], u=ev[1], t=ev[2], cls='', txt='';
      if (a==='enter') { count1++; inside++; cls='status-enter'; txt='✅ Вход'; }
      else if (a==='exit') { count2++; inside--; cls='status-exit'; txt='🚪 Выход'; }
      else if (a==='register'||a==='register_request') { cls='status-register'; txt='📝 Регистрация'; }
      else if (a==='blocked_enter') { cls='status-blocked'; txt='⛔ Блокировка входа'; }
      else if (a==='blocked_exit') { cls='status-blocked'; txt='⛔ Блокировка выхода'; }
      else { cls='status-blocked'; txt='⛔ '+a; }
      list.innerHTML += `<tr><td class="${cls}">${txt}</td><td>${u}</td><td>${t}</td></tr>`;
    });
  }
  document.getElementById('totalEvents').textContent = total;
  document.getElementById('currentPeople').textContent = inside < 0 ? 0 : inside;
  document.getElementById('inMatch').textContent = count1;
  document.getElementById('outCount').textContent = count2;
  document.getElementById('lastEventTime').textContent = last;

  const usersList = document.getElementById('usersList');
  usersList.innerHTML = '';
  if (data.users && data.users.length > 0) {
    data.users.forEach(u => {
      const status = u.is_inside ? 'Внутри' : 'Снаружи';
      const color = u.is_inside ? '#2ecc71' : '#f1c40f';
      usersList.innerHTML += `<tr><td>${u.name} ${u.surname}</td><td>${u.uid}</td><td style="color:${color}">${status}</td></tr>`;
    });
  } else {
    usersList.innerHTML = '<tr><td colspan="3" style="color:#aaa;">Нет пользователей</td></tr>';
  }
  const sr = await fetch(API_URL + '/api/registration-status');
  const sd = await sr.json();
  regOpen = sd.open; updateRegUI();
}
setInterval(loadData, 2000); loadData();
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
    c.execute("SELECT timestamp FROM events ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    last_time = row[0] if row else ""
    conn.close()
    return jsonify({
        "inside_count": inside_count,
        "last_time": last_time,
        "registration_open": registration_open
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
