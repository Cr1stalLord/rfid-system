from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3
import datetime
import os

app = Flask(__name__)
CORS(app)

DB_FILE = 'rfid_logs.db'

# ==================== HTML ШАБЛОН АДМИН-САЙТА (с управлением) ====================
ADMIN_TEMPLATE = """
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
#lastAction {
  padding: 15px;
  background: rgba(255,255,255,0.05);
  border-radius: 8px;
  margin-top: 15px;
  font-size: 0.9em;
  color: #aaa;
}
#lastAction strong { color: white; }
table { width: 100%; border-collapse: collapse; margin-top: 10px; }
th { text-align: left; padding: 12px; border-bottom: 2px solid rgba(255,255,255,0.1); color: #aaa; font-weight: 400; font-size: 0.9em; }
td { padding: 12px; border-bottom: 1px solid rgba(255,255,255,0.05); vertical-align: middle; }
.status-enter { color: #2ecc71; }
.status-exit { color: #f1c40f; }
.status-blocked { color: #e74c3c; }
.status-register { color: #3498db; }

.reg-block {
  margin-top: 20px;
  padding: 20px;
  background: rgba(255,255,255,0.03);
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.1);
}
.reg-block .indicator {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 15px;
}
.led {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: inline-block;
  transition: 0.3s;
}
.led-green { background: #2ecc71; box-shadow: 0 0 15px #2ecc71; }
.led-red { background: #e74c3c; box-shadow: 0 0 15px #e74c3c; }
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
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-green { background: #2ecc71; }
.btn-danger { background: #e74c3c; padding: 5px 12px; font-size: 0.8em; }
.btn-sm { padding: 5px 12px; font-size: 0.8em; }
.input-group { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
.input-group input {
  flex: 1;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid #555;
  background: #222;
  color: white;
  min-width: 150px;
}
.reg-message { margin-top: 10px; font-size: 0.95em; }
.user-actions { display: flex; gap: 8px; align-items: center; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🔐 RFID Админ-панель</h1>
  </div>

  <div class="stats">
    <div class="stat-card"><div class="number" id="totalEvents">0</div><div class="label">📊 Всего событий</div></div>
    <div class="stat-card" style="border: 1px solid #2ecc71;"><div class="number" id="currentPeople">0</div><div class="label">👤 Сейчас внутри</div></div>
    <div class="stat-card"><div class="number" id="inMatch">0</div><div class="label">✅ Входов</div></div>
    <div class="stat-card"><div class="number" id="outCount">0</div><div class="label">🚪 Выходов</div></div>
    <div class="stat-card"><div class="number" id="lastEventTime">--:--</div><div class="label">🕒 Последнее событие</div></div>
  </div>

  <div class="grid-2">
    <!-- Лента событий -->
    <div>
      <div class="card">
        <h2>📋 Лента событий</h2>
        <div id="lastAction"><strong>Ожидание данных...</strong></div>
        <div style="overflow-x: auto; max-height: 400px; overflow-y: auto;">
          <table>
            <thead><tr><th>Действие</th><th>Карта</th><th>Время</th></tr></thead>
            <tbody id="eventsList"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Управление -->
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

          <div id="registrationForm" style="display: none; margin-top: 20px; border-top: 1px solid #444; padding-top: 20px;">
            <h3 style="color: #f5a623;">Зарегистрировать новую карту</h3>
            <p style="color: #aaa; font-size: 0.9em;">Приложите карту к RFID 3, затем введите имя и фамилию.</p>
            <div class="input-group">
              <input type="text" id="regName" placeholder="Имя">
              <input type="text" id="regSurname" placeholder="Фамилия">
              <button class="btn btn-green" id="confirmRegBtn">Подтвердить</button>
            </div>
            <div id="regMessage" class="reg-message"></div>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top: 20px;">
        <h2>📋 Пользователи</h2>
        <div style="max-height: 300px; overflow-y: auto;">
          <table>
            <thead><tr><th>Имя</th><th>UID</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody id="usersList"></tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
const API_URL = window.location.origin;
let regOpen = false;
let pendingUid = null;

function updateRegUI() {
  const led = document.getElementById('regLed');
  const text = document.getElementById('regStatusText');
  const btn = document.getElementById('toggleRegBtn');
  const form = document.getElementById('registrationForm');

  if (regOpen) {
    led.className = 'led led-green';
    text.textContent = 'Открыта';
    btn.textContent = 'Закрыть регистрацию';
    form.style.display = 'block';
  } else {
    led.className = 'led led-red';
    text.textContent = 'Закрыта';
    btn.textContent = 'Открыть регистрацию';
    form.style.display = 'none';
    document.getElementById('regMessage').innerHTML = '';
  }
}

document.getElementById('toggleRegBtn').addEventListener('click', async () => {
  try {
    const resp = await fetch(API_URL + '/toggle-registration', { method: 'POST' });
    const data = await resp.json();
    regOpen = data.open;
    updateRegUI();
  } catch (e) { console.error(e); }
});

document.getElementById('confirmRegBtn').addEventListener('click', async () => {
  const name = document.getElementById('regName').value.trim();
  const surname = document.getElementById('regSurname').value.trim();
  const msg = document.getElementById('regMessage');

  if (!name || !surname) {
    msg.innerHTML = '<span style="color: #f1c40f;">Введите имя и фамилию</span>';
    return;
  }
  if (!pendingUid) {
    msg.innerHTML = '<span style="color: #e74c3c;">Сначала приложите карту к RFID 3</span>';
    return;
  }

  try {
    const resp = await fetch(API_URL + '/confirm-registration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uid: pendingUid, name, surname })
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      msg.innerHTML = '<span style="color: #2ecc71;">✅ Пользователь зарегистрирован!</span>';
      document.getElementById('regName').value = '';
      document.getElementById('regSurname').value = '';
      pendingUid = null;
      loadData();
    } else {
      msg.innerHTML = `<span style="color: #e74c3c;">❌ ${data.message || 'Ошибка'}</span>`;
    }
  } catch (e) {
    msg.innerHTML = '<span style="color: #e74c3c;">Ошибка соединения</span>';
  }
});

async function deleteUser(uid) {
  if (!confirm(`Удалить пользователя с UID ${uid}?`)) return;
  try {
    const resp = await fetch(API_URL + '/delete-user?uid=' + uid, { method: 'DELETE' });
    const data = await resp.json();
    if (data.status === 'ok') loadData();
    else alert('Ошибка: ' + data.message);
  } catch (e) { alert('Ошибка соединения'); }
}

async function loadData() {
  try {
    const resp = await fetch(API_URL + '/api/get-users');
    const data = await resp.json();

    const list = document.getElementById('eventsList');
    list.innerHTML = '';
    let total = 0, count1 = 0, count2 = 0, currentInside = 0, lastTime = '--:--';

    if (data.events && data.events.length > 0) {
      total = data.events.length;
      lastTime = data.events[0][2].substring(11, 16);
      data.events.forEach(ev => {
        let action = ev[0], uid = ev[1], time = ev[2];
        let statusClass = '', statusText = '';
        if (action === 'enter') { count1++; currentInside++; statusClass = 'status-enter'; statusText = '✅ Вход'; }
        else if (action === 'exit') { count2++; currentInside--; statusClass = 'status-exit'; statusText = '🚪 Выход'; }
        else if (action === 'register' || action === 'register_request') { statusClass = 'status-register'; statusText = '📝 Регистрация'; }
        else if (action === 'blocked_enter') { statusClass = 'status-blocked'; statusText = '⛔ Блокировка входа'; }
        else if (action === 'blocked_exit') { statusClass = 'status-blocked'; statusText = '⛔ Блокировка выхода'; }
        else { statusClass = 'status-blocked'; statusText = '⛔ ' + action; }
        list.innerHTML += `<tr><td class="${statusClass}">${statusText}</td><td>${uid}</td><td>${time}</td></tr>`;
      });
      document.getElementById('lastAction').innerHTML = `<strong>🟢 Система работает</strong> (последнее: ${lastTime})`;
    } else {
      document.getElementById('lastAction').innerHTML = `<strong>⏳ Нет данных</strong>`;
    }
    document.getElementById('totalEvents').textContent = total;
    document.getElementById('currentPeople').textContent = currentInside < 0 ? 0 : currentInside;
    document.getElementById('inMatch').textContent = count1;
    document.getElementById('outCount').textContent = count2;
    document.getElementById('lastEventTime').textContent = lastTime;

    const usersList = document.getElementById('usersList');
    usersList.innerHTML = '';
    if (data.users && data.users.length > 0) {
      data.users.forEach(u => {
        const status = u.is_inside ? 'Внутри' : 'Снаружи';
        const color = u.is_inside ? '#2ecc71' : '#f1c40f';
        usersList.innerHTML += `<tr>
          <td>${u.name} ${u.surname}</td>
          <td>${u.uid}</td>
          <td style="color:${color}">${status}</td>
          <td><button class="btn btn-danger btn-sm" onclick="deleteUser('${u.uid}')">🗑️</button></td>
        </tr>`;
      });
    } else {
      usersList.innerHTML = '<tr><td colspan="4" style="color:#aaa;">Нет пользователей</td></tr>';
    }

    const statusResp = await fetch(API_URL + '/api/registration-status');
    const statusData = await statusResp.json();
    regOpen = statusData.open;
    pendingUid = statusData.pending_uid || null;
    updateRegUI();

    if (pendingUid) {
      document.getElementById('regMessage').innerHTML = `<span style="color: #3498db;">Карта ${pendingUid} ожидает регистрации</span>`;
    } else if (regOpen) {
      document.getElementById('regMessage').innerHTML = '<span style="color: #aaa;">Приложите карту к RFID 3</span>';
    }
  } catch (e) {
    console.error(e);
    document.getElementById('lastAction').innerHTML = `<strong>❌ Ошибка подключения</strong>`;
  }
}

setInterval(loadData, 2000);
loadData();
</script>
</body>
</html>
"""

# ==================== HTML ШАБЛОН ПУБЛИЧНОГО САЙТА (только статистика и регистрация) ====================
PUBLIC_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>RFID Статус входа</title>
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
.container {
  max-width: 600px;
  width: 100%;
  text-align: center;
}
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
.reg-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 15px;
  margin: 10px 0;
}
.led {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: inline-block;
  transition: 0.3s;
}
.led-green { background: #2ecc71; box-shadow: 0 0 15px #2ecc71; }
.led-red { background: #e74c3c; box-shadow: 0 0 15px #e74c3c; }

.reg-form {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid rgba(255,255,255,0.1);
}
.input-group { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; margin-top: 10px; }
.input-group input {
  padding: 10px;
  border-radius: 8px;
  border: 1px solid #555;
  background: #222;
  color: white;
  min-width: 120px;
  flex: 1;
}
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
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-green { background: #2ecc71; }

.reg-message { margin-top: 10px; font-size: 0.95em; color: #aaa; }

.footer {
  margin-top: 30px;
  color: #555;
  font-size: 0.8em;
}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🏢 RFID Контроль доступа</h1>
    <p style="color: #aaa;">Текущий статус системы</p>
  </div>

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
    <div class="reg-status">
      <span>Статус:</span>
      <span class="led" id="regLed"></span>
      <span id="regStatusText">Закрыта</span>
    </div>

    <div class="reg-form" id="regForm">
      <p style="color: #aaa; font-size: 0.9em;">Приложите карту к RFID 3 и введите данные</p>
      <div class="input-group">
        <input type="text" id="regName" placeholder="Имя">
        <input type="text" id="regSurname" placeholder="Фамилия">
        <button class="btn btn-green" id="regBtn">Зарегистрироваться</button>
      </div>
      <div id="regMessage" class="reg-message"></div>
    </div>
  </div>

  <div class="footer">
    <span>Система работает</span>
  </div>
</div>

<script>
const API_URL = window.location.origin;
let pendingUid = null;

document.getElementById('regBtn').addEventListener('click', async () => {
  const name = document.getElementById('regName').value.trim();
  const surname = document.getElementById('regSurname').value.trim();
  const msg = document.getElementById('regMessage');

  if (!name || !surname) {
    msg.innerHTML = '<span style="color: #f1c40f;">Введите имя и фамилию</span>';
    return;
  }
  if (!pendingUid) {
    msg.innerHTML = '<span style="color: #e74c3c;">Сначала приложите карту к RFID 3</span>';
    return;
  }

  try {
    const resp = await fetch(API_URL + '/confirm-registration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uid: pendingUid, name, surname })
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      msg.innerHTML = '<span style="color: #2ecc71;">✅ Вы зарегистрированы!</span>';
      document.getElementById('regName').value = '';
      document.getElementById('regSurname').value = '';
      pendingUid = null;
      loadData();
    } else {
      msg.innerHTML = `<span style="color: #e74c3c;">❌ ${data.message || 'Ошибка'}</span>`;
    }
  } catch (e) {
    msg.innerHTML = '<span style="color: #e74c3c;">Ошибка соединения</span>';
  }
});

async function loadData() {
  try {
    const resp = await fetch(API_URL + '/api/public-data');
    const data = await resp.json();

    document.getElementById('currentPeople').textContent = data.inside_count || 0;
    document.getElementById('lastEventTime').textContent = data.last_time ? data.last_time.substring(11, 16) : '--:--';

    const led = document.getElementById('regLed');
    const text = document.getElementById('regStatusText');
    const regForm = document.getElementById('regForm');
    const msg = document.getElementById('regMessage');

    if (data.registration_open) {
      led.className = 'led led-green';
      text.textContent = 'Открыта';
      regForm.style.display = 'block';
    } else {
      led.className = 'led led-red';
      text.textContent = 'Закрыта';
      regForm.style.display = 'none';
      msg.innerHTML = '<span style="color: #e74c3c;">🔒 Регистрация закрыта</span>';
    }

    pendingUid = data.pending_uid || null;
    if (pendingUid && data.registration_open) {
      msg.innerHTML = `<span style="color: #3498db;">Карта ${pendingUid} ожидает регистрации</span>`;
    } else if (data.registration_open) {
      msg.innerHTML = '<span style="color: #aaa;">Приложите карту к RFID 3</span>';
    }
  } catch (e) {
    console.error(e);
  }
}

setInterval(loadData, 2000);
loadData();
</script>
</body>
</html>
"""

# ==================== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ====================
def init_db():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print("🗑️ Старая база данных удалена.")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE card_status (uid TEXT PRIMARY KEY, is_inside INTEGER NOT NULL)''')
    c.execute('''CREATE TABLE users (uid TEXT PRIMARY KEY, name TEXT, surname TEXT, is_inside INTEGER DEFAULT 0, exit_count INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, uid TEXT NOT NULL, timestamp TEXT NOT NULL)''')
    conn.commit()
    conn.close()
    print("✅ Новая база данных создана.")

init_db()

registration_open = False
pending_uid = None

# ==================== API ====================
@app.route('/toggle-registration', methods=['POST'])
def toggle_registration():
    global registration_open, pending_uid
    registration_open = not registration_open
    if not registration_open:
        pending_uid = None
    return jsonify({"open": registration_open})

@app.route('/api/registration-status', methods=['GET'])
def registration_status():
    return jsonify({"open": registration_open, "pending_uid": pending_uid})

@app.route('/confirm-registration', methods=['POST'])
def confirm_registration():
    global pending_uid
    data = request.get_json()
    uid = data.get('uid')
    name = data.get('name')
    surname = data.get('surname')

    if not uid or not name or not surname:
        return jsonify({"status": "error", "message": "Не все поля заполнены"}), 400
    if pending_uid != uid:
        return jsonify({"status": "error", "message": "UID не совпадает с ожидаемым"}), 400

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT uid FROM users WHERE uid = ?", (uid,))
    if c.fetchone():
        pending_uid = None
        conn.close()
        return jsonify({"status": "error", "message": "Карта уже зарегистрирована"}), 400

    c.execute("INSERT INTO users (uid, name, surname, is_inside, exit_count) VALUES (?, ?, ?, 0, 0)", (uid, name, surname))
    c.execute("REPLACE INTO card_status (uid, is_inside) VALUES (?, 0)", (uid,))
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('register', ?, ?)", (uid, now))
    conn.commit()
    conn.close()

    pending_uid = None
    return jsonify({"status": "ok", "message": "Пользователь зарегистрирован"})

@app.route('/delete-user', methods=['DELETE'])
def delete_user():
    uid = request.args.get('uid')
    if not uid:
        return jsonify({"status": "error", "message": "Не указан UID"}), 400
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE uid = ?", (uid,))
    if c.rowcount == 0:
        conn.close()
        return jsonify({"status": "error", "message": "Пользователь не найден"}), 404
    c.execute("DELETE FROM card_status WHERE uid = ?", (uid,))
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('deleted', ?, ?)", (uid, now))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "message": "Пользователь удалён"})

@app.route('/rfid', methods=['GET'])
def handle_rfid():
    global pending_uid, registration_open
    reader = request.args.get('reader')
    uid = request.args.get('uid')
    action = request.args.get('action')

    if not reader or not uid:
        return jsonify({"error": "Missing reader or uid"}), 400

    print(f"📥 Запрос: reader={reader}, uid={uid}, action={action}")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if reader == "3" or action == "REGISTER":
        if not registration_open:
            conn.close()
            return jsonify({"status": "registration_closed", "message": "Регистрация закрыта"}), 403
        c.execute("SELECT uid FROM users WHERE uid = ?", (uid,))
        if c.fetchone():
            conn.close()
            return jsonify({"status": "already_registered", "message": "Карта уже зарегистрирована"}), 400
        pending_uid = uid
        c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('register_request', ?, ?)", (uid, now))
        conn.commit()
        conn.close()
        print(f"✅ Ожидание регистрации для {uid}")
        return jsonify({"status": "waiting_for_name", "uid": uid, "message": "Ожидайте ввода имени"})

    c.execute("SELECT name, surname, is_inside, exit_count FROM users WHERE uid = ?", (uid,))
    user = c.fetchone()
    if not user:
        conn.close()
        c = conn.cursor()
        c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('unregistered_attempt', ?, ?)", (uid, now))
        conn.commit()
        conn.close()
        return jsonify({"status": "not_registered", "message": "Карта не зарегистрирована"}), 403

    name, surname, is_inside, exit_count = user
    action_performed = None
    new_inside = is_inside
    message = ""

    if reader == "1":
        if is_inside:
            action_performed = "blocked_enter"
            c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('blocked_enter', ?, ?)", (uid, now))
            message = "Вы уже внутри системы"
        else:
            action_performed = "enter"
            new_inside = 1
            c.execute("UPDATE users SET is_inside = 1 WHERE uid = ?", (uid,))
            c.execute("REPLACE INTO card_status (uid, is_inside) VALUES (?, 1)", (uid,))
            c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('enter', ?, ?)", (uid, now))
            message = "Вход разрешён"

    elif reader == "2":
        if not is_inside:
            action_performed = "blocked_exit"
            c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('blocked_exit', ?, ?)", (uid, now))
            message = "Вы уже снаружи системы"
        else:
            action_performed = "exit"
            new_inside = 0
            exit_count += 1
            c.execute("UPDATE users SET is_inside = 0, exit_count = ? WHERE uid = ?", (exit_count, uid))
            c.execute("REPLACE INTO card_status (uid, is_inside) VALUES (?, 0)", (uid,))
            c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('exit', ?, ?)", (uid, now))
            message = "Выход разрешён"

    conn.commit()
    conn.close()
    return jsonify({
        "status": "ok",
        "uid": uid,
        "action": action_performed,
        "name": name,
        "surname": surname,
        "inside": new_inside,
        "exit_count": exit_count,
        "message": message,
        "time": now
    })

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
        "registration_open": registration_open,
        "pending_uid": pending_uid
    })

# ==================== ГЛАВНЫЕ СТРАНИЦЫ ====================
@app.route('/')
def public_home():
    return render_template_string(PUBLIC_TEMPLATE)

@app.route('/admin')
def admin_home():
    return render_template_string(ADMIN_TEMPLATE)

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    print("\n=== RFID Умный контроль запущен ===")
    print("📌 Публичный сайт (для всех): http://localhost:5000")
    print("📌 Админ-панель (только локально): http://localhost:5000/admin")
    print("======================================\n")
    app.run(host='0.0.0.0', port=5000, debug=True)