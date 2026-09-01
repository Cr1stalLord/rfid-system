# -*- coding: utf-8 -*-
"""
============================================================
 Система контроля доступа — Flask сервер (один файл)
============================================================
 Локальный запуск:
     pip install flask
     python server.py
     -> http://localhost:5000/         (публичная страница)
     -> http://localhost:5000/admin    (админ-панель)

 Деплой на Render.com (без дополнительных файлов):
     1. New -> Web Service -> подключить репозиторий с этим файлом.
     2. Build Command:  pip install flask gunicorn
     3. Start Command:  gunicorn server:app --workers 1 --bind 0.0.0.0:$PORT
        (--workers 1 обязателен: состояние регистрации хранится
         в памяти процесса, при нескольких воркерах оно "разъедется")
     4. В прошивке ESP32 указать выданный Render URL в serverUrl.
============================================================
"""

import os
import sqlite3
import threading
from datetime import datetime

from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "access_control.db")
db_lock = threading.Lock()

# Состояние регистрации хранится в памяти процесса
registration_open = False
pending_uid = None


# ============================================================
#  РАБОТА С БАЗОЙ ДАННЫХ
# ============================================================
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            uid TEXT PRIMARY KEY,
            name TEXT DEFAULT 'User',
            surname TEXT DEFAULT '',
            is_inside INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            uid TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_event(action, uid):
    conn = get_db()
    conn.execute(
        "INSERT INTO events (action, uid, timestamp) VALUES (?, ?, ?)",
        (action, uid, now_str()),
    )
    conn.commit()
    conn.close()


def get_or_create_user(uid):
    """Возвращает (row, created). Если карты не было — создаёт с именем 'User'."""
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE uid = ?", (uid,)).fetchone()
    created = False
    if row is None:
        conn.execute(
            "INSERT INTO users (uid, name, surname, is_inside) VALUES (?, 'User', '', 0)",
            (uid,),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE uid = ?", (uid,)).fetchone()
        created = True
    conn.close()
    return row, created


def set_inside(uid, value):
    conn = get_db()
    conn.execute("UPDATE users SET is_inside = ? WHERE uid = ?", (value, uid))
    conn.commit()
    conn.close()


# ============================================================
#  API: /rfid  — обработка запросов от ESP32
# ============================================================
@app.route("/rfid")
def rfid():
    global pending_uid

    reader = request.args.get("reader")
    uid = request.args.get("uid")

    if not reader or not uid:
        return jsonify({"status": "error", "message": "Параметры reader и uid обязательны"}), 400

    uid = uid.upper()

    if reader not in ("1", "2", "3"):
        return jsonify({"status": "error", "message": "reader должен быть 1, 2 или 3"}), 400

    with db_lock:
        user, created = get_or_create_user(uid)
        if created:
            log_event("register", uid)

        # ---------------- RFID1: ВХОД ----------------
        if reader == "1":
            if user["is_inside"] == 1:
                status, message = "denied", f"Карта {uid} уже отмечена как 'внутри'"
            else:
                set_inside(uid, 1)
                log_event("entry", uid)
                fio = (user["name"] + " " + user["surname"]).strip()
                status, message = "ok", f"Вход разрешён: {fio}"

        # ---------------- RFID2: ВЫХОД ----------------
        elif reader == "2":
            if user["is_inside"] == 0:
                status, message = "denied", f"Карта {uid} не отмечена как 'внутри'"
            else:
                set_inside(uid, 0)
                log_event("exit", uid)
                fio = (user["name"] + " " + user["surname"]).strip()
                status, message = "ok", f"Выход разрешён: {fio}"

        # ---------------- RFID3: РЕГИСТРАЦИЯ ----------------
        else:  # reader == "3"
            if registration_open:
                pending_uid = uid
                log_event("registration_scan", uid)
                status, message = "ok", f"Карта {uid} ожидает ввода имени на сайте"
            else:
                status, message = "denied", "Регистрация закрыта администратором"

    return jsonify({"status": status, "uid": uid, "message": message})


# ============================================================
#  API: список пользователей и событий (для админки)
# ============================================================
@app.route("/api/get-users")
def api_get_users():
    conn = get_db()
    users = [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY uid").fetchall()]
    events = [dict(r) for r in conn.execute(
        "SELECT * FROM events ORDER BY id DESC LIMIT 200"
    ).fetchall()]

    total_events = conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
    inside_count = conn.execute("SELECT COUNT(*) c FROM users WHERE is_inside = 1").fetchone()["c"]
    entries = conn.execute("SELECT COUNT(*) c FROM events WHERE action = 'entry'").fetchone()["c"]
    exits = conn.execute("SELECT COUNT(*) c FROM events WHERE action = 'exit'").fetchone()["c"]
    conn.close()

    stats = {
        "total_events": total_events,
        "inside_count": inside_count,
        "entries": entries,
        "exits": exits,
        "total_users": len(users),
    }

    return jsonify({"users": users, "events": events, "stats": stats})


# ============================================================
#  API: публичные данные для главной страницы
# ============================================================
@app.route("/api/public-data")
def api_public_data():
    conn = get_db()
    inside_count = conn.execute("SELECT COUNT(*) c FROM users WHERE is_inside = 1").fetchone()["c"]
    last_event = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()

    return jsonify({
        "inside_count": inside_count,
        "last_event_time": last_event["timestamp"] if last_event else None,
        "last_event_action": last_event["action"] if last_event else None,
        "last_event_uid": last_event["uid"] if last_event else None,
        "registration_open": registration_open,
    })


# ============================================================
#  API: статус регистрации (открыта/закрыта + ожидающий UID)
# ============================================================
@app.route("/api/registration-status")
def api_registration_status():
    return jsonify({
        "registration_open": registration_open,
        "pending_uid": pending_uid,
    })


# ============================================================
#  API: открыть/закрыть регистрацию (кнопка в админке)
# ============================================================
@app.route("/toggle-registration", methods=["POST"])
def toggle_registration():
    global registration_open, pending_uid
    with db_lock:
        registration_open = not registration_open
        if not registration_open:
            pending_uid = None
    return jsonify({"registration_open": registration_open, "pending_uid": pending_uid})


# ============================================================
#  API: подтверждение регистрации (форма Имя/Фамилия на сайте)
# ============================================================
@app.route("/confirm-registration", methods=["POST"])
def confirm_registration():
    global pending_uid, registration_open

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    surname = (data.get("surname") or "").strip()

    with db_lock:
        if not pending_uid:
            return jsonify({"status": "error", "message": "Нет карты, ожидающей регистрации. Приложите карту к RFID3."}), 400
        if not name:
            return jsonify({"status": "error", "message": "Поле 'Имя' обязательно для заполнения"}), 400

        conn = get_db()
        conn.execute(
            "UPDATE users SET name = ?, surname = ? WHERE uid = ?",
            (name, surname, pending_uid),
        )
        conn.commit()
        conn.close()

        log_event("registration_confirm", pending_uid)

        confirmed_uid = pending_uid
        pending_uid = None
        registration_open = False

    return jsonify({"status": "ok", "uid": confirmed_uid, "message": "Регистрация завершена"})


# ============================================================
#  HTML: ПУБЛИЧНАЯ СТРАНИЦА
# ============================================================
PUBLIC_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Система контроля доступа</title>
<style>
  :root{
    --bg:#0e1016; --card:#171a23; --card2:#1e2230; --border:#2a2f3f;
    --text:#e7e9ee; --muted:#8a90a2; --accent:#5b8cff; --green:#3ddc97;
    --red:#ff5c7a; --yellow:#ffc857;
  }
  *{box-sizing:border-box;}
  body{
    margin:0; min-height:100vh; background:
      radial-gradient(circle at 20% 0%, #1a1f2e 0%, var(--bg) 45%);
    color:var(--text); font-family:'Segoe UI',Roboto,Arial,sans-serif;
    display:flex; justify-content:center; padding:32px 16px;
  }
  .wrap{width:100%; max-width:560px;}
  h1{font-size:22px; font-weight:600; text-align:center; margin:0 0 28px;
     letter-spacing:.3px;}
  h1 span{color:var(--accent);}
  .card{
    background:linear-gradient(180deg, var(--card2), var(--card));
    border:1px solid var(--border); border-radius:16px;
    padding:22px; margin-bottom:16px; box-shadow:0 10px 30px rgba(0,0,0,.35);
  }
  .grid2{display:grid; grid-template-columns:1fr 1fr; gap:16px;}
  .stat-label{color:var(--muted); font-size:13px; text-transform:uppercase;
     letter-spacing:.06em; margin-bottom:6px;}
  .stat-value{font-size:32px; font-weight:700;}
  .stat-value.inside{color:var(--green);}
  .stat-sub{font-size:13px; color:var(--muted); margin-top:4px;}
  .badge{
    display:inline-flex; align-items:center; gap:8px; padding:6px 14px;
    border-radius:999px; font-size:13px; font-weight:600;
  }
  .badge.open{background:rgba(61,220,151,.12); color:var(--green); border:1px solid rgba(61,220,151,.35);}
  .badge.closed{background:rgba(255,92,122,.12); color:var(--red); border:1px solid rgba(255,92,122,.35);}
  .dot{width:8px; height:8px; border-radius:50%; background:currentColor;}
  form{display:flex; flex-direction:column; gap:12px; margin-top:14px;}
  input{
    background:#11131a; border:1px solid var(--border); border-radius:10px;
    padding:12px 14px; color:var(--text); font-size:14px; outline:none;
    transition:border-color .15s;
  }
  input:focus{border-color:var(--accent);}
  button{
    background:linear-gradient(180deg, #6d95ff, var(--accent));
    color:#fff; border:none; border-radius:10px; padding:12px 14px;
    font-size:14px; font-weight:600; cursor:pointer; transition:opacity .15s;
  }
  button:disabled{opacity:.4; cursor:not-allowed;}
  button:hover:not(:disabled){opacity:.9;}
  .hint{font-size:13px; color:var(--muted); line-height:1.5;}
  .pending{
    background:rgba(255,200,87,.1); border:1px solid rgba(255,200,87,.3);
    color:var(--yellow); border-radius:10px; padding:10px 12px; font-size:13px;
    margin-top:10px;
  }
  .msg{margin-top:10px; font-size:13px; border-radius:10px; padding:10px 12px; display:none;}
  .msg.ok{background:rgba(61,220,151,.12); color:var(--green); display:block;}
  .msg.err{background:rgba(255,92,122,.12); color:var(--red); display:block;}
  .footer-note{text-align:center; color:var(--muted); font-size:12px; margin-top:20px;}
</style>
</head>
<body>
<div class="wrap">
  <h1>Система контроля <span>доступа</span></h1>

  <div class="card grid2">
    <div>
      <div class="stat-label">Внутри сейчас</div>
      <div class="stat-value inside" id="insideCount">—</div>
    </div>
    <div>
      <div class="stat-label">Последнее событие</div>
      <div class="stat-value" id="lastEventTime" style="font-size:18px;">—</div>
      <div class="stat-sub" id="lastEventAction">—</div>
    </div>
  </div>

  <div class="card">
    <div class="stat-label">Статус регистрации</div>
    <div id="regBadge" class="badge closed" style="margin-top:8px;">
      <span class="dot"></span><span id="regBadgeText">Закрыта</span>
    </div>

    <div id="pendingBox" class="pending" style="display:none;"></div>

    <form id="regForm">
      <input type="text" id="fname" placeholder="Имя" autocomplete="off">
      <input type="text" id="fsurname" placeholder="Фамилия" autocomplete="off">
      <button type="submit" id="submitBtn">Зарегистрироваться</button>
    </form>
    <div class="hint" style="margin-top:10px;">
      Чтобы зарегистрировать новую карту: администратор открывает регистрацию,
      вы прикладываете карту к считывателю №3, затем заполняете форму выше.
    </div>
    <div class="msg" id="formMsg"></div>
  </div>

  <div class="footer-note">Обновление данных каждые 2 секунды</div>
</div>

<script>
async function refreshPublic() {
  try {
    const [pubRes, regRes] = await Promise.all([
      fetch('/api/public-data'), fetch('/api/registration-status')
    ]);
    const pub = await pubRes.json();
    const reg = await regRes.json();

    document.getElementById('insideCount').textContent = pub.inside_count;
    document.getElementById('lastEventTime').textContent = pub.last_event_time || '—';

    const actionsRu = {
      entry: 'Вход', exit: 'Выход', register: 'Автоматическая регистрация',
      registration_scan: 'Карта приложена к регистрации',
      registration_confirm: 'Регистрация подтверждена'
    };
    document.getElementById('lastEventAction').textContent = pub.last_event_action
      ? (actionsRu[pub.last_event_action] || pub.last_event_action) + (pub.last_event_uid ? (' · ' + pub.last_event_uid) : '')
      : '—';

    const badge = document.getElementById('regBadge');
    const badgeText = document.getElementById('regBadgeText');
    if (reg.registration_open) {
      badge.className = 'badge open';
      badgeText.textContent = 'Открыта';
    } else {
      badge.className = 'badge closed';
      badgeText.textContent = 'Закрыта';
    }

    const pendingBox = document.getElementById('pendingBox');
    const submitBtn = document.getElementById('submitBtn');
    if (reg.registration_open && reg.pending_uid) {
      pendingBox.style.display = 'block';
      pendingBox.textContent = 'Карта обнаружена (UID: ' + reg.pending_uid + '). Заполните форму и нажмите кнопку.';
      submitBtn.disabled = false;
    } else if (reg.registration_open && !reg.pending_uid) {
      pendingBox.style.display = 'block';
      pendingBox.textContent = 'Регистрация открыта. Приложите карту к считывателю №3.';
      submitBtn.disabled = true;
    } else {
      pendingBox.style.display = 'none';
      submitBtn.disabled = true;
    }
  } catch (e) { /* тихо игнорируем сетевые сбои при поллинге */ }
}

document.getElementById('regForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = document.getElementById('fname').value.trim();
  const surname = document.getElementById('fsurname').value.trim();
  const msgBox = document.getElementById('formMsg');

  try {
    const res = await fetch('/confirm-registration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, surname })
    });
    const data = await res.json();
    if (data.status === 'ok') {
      msgBox.className = 'msg ok';
      msgBox.textContent = 'Готово! Карта ' + data.uid + ' зарегистрирована.';
      document.getElementById('fname').value = '';
      document.getElementById('fsurname').value = '';
    } else {
      msgBox.className = 'msg err';
      msgBox.textContent = data.message || 'Ошибка регистрации';
    }
  } catch (err) {
    msgBox.className = 'msg err';
    msgBox.textContent = 'Ошибка сети';
  }
  refreshPublic();
});

refreshPublic();
setInterval(refreshPublic, 2000);
</script>
</body>
</html>
"""


# ============================================================
#  HTML: АДМИН-ПАНЕЛЬ
# ============================================================
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Админ-панель — Контроль доступа</title>
<style>
  :root{
    --bg:#0e1016; --card:#171a23; --card2:#1e2230; --border:#2a2f3f;
    --text:#e7e9ee; --muted:#8a90a2; --accent:#5b8cff; --green:#3ddc97;
    --red:#ff5c7a; --yellow:#ffc857;
  }
  *{box-sizing:border-box;}
  body{
    margin:0; min-height:100vh; background:
      radial-gradient(circle at 80% 0%, #1a1f2e 0%, var(--bg) 45%);
    color:var(--text); font-family:'Segoe UI',Roboto,Arial,sans-serif;
    padding:28px 20px 60px;
  }
  .wrap{max-width:1100px; margin:0 auto;}
  .top{display:flex; justify-content:space-between; align-items:center;
       flex-wrap:wrap; gap:14px; margin-bottom:24px;}
  h1{font-size:22px; font-weight:600; margin:0;}
  h1 span{color:var(--accent);}
  a.pubLink{color:var(--muted); font-size:13px; text-decoration:none; border-bottom:1px dashed var(--border);}
  .btn{
    background:linear-gradient(180deg, #6d95ff, var(--accent));
    color:#fff; border:none; border-radius:10px; padding:11px 18px;
    font-size:14px; font-weight:600; cursor:pointer;
  }
  .btn.danger{background:linear-gradient(180deg, #ff7a92, var(--red));}
  .stats{display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-bottom:22px;}
  .stat-card{
    background:linear-gradient(180deg, var(--card2), var(--card));
    border:1px solid var(--border); border-radius:14px; padding:16px;
  }
  .stat-label{color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.05em;}
  .stat-value{font-size:26px; font-weight:700; margin-top:6px;}
  .stat-value.green{color:var(--green);}
  .stat-value.blue{color:var(--accent);}
  .stat-value.red{color:var(--red);}
  .columns{display:grid; grid-template-columns:1.1fr 1fr; gap:18px;}
  @media (max-width: 860px){ .columns{grid-template-columns:1fr;} }
  .panel{
    background:linear-gradient(180deg, var(--card2), var(--card));
    border:1px solid var(--border); border-radius:16px; padding:18px;
  }
  .panel h2{font-size:15px; margin:0 0 14px; color:var(--text); display:flex; align-items:center; justify-content:space-between;}
  .badge{padding:4px 10px; border-radius:999px; font-size:12px; font-weight:600;}
  .badge.open{background:rgba(61,220,151,.12); color:var(--green); border:1px solid rgba(61,220,151,.35);}
  .badge.closed{background:rgba(255,92,122,.12); color:var(--red); border:1px solid rgba(255,92,122,.35);}
  table{width:100%; border-collapse:collapse; font-size:13px;}
  th{text-align:left; color:var(--muted); font-weight:500; padding:8px 6px; border-bottom:1px solid var(--border);}
  td{padding:9px 6px; border-bottom:1px solid rgba(255,255,255,.04);}
  tr:last-child td{border-bottom:none;}
  .uid{font-family:'Consolas',monospace; color:var(--accent); font-size:12px;}
  .tag{padding:3px 9px; border-radius:999px; font-size:11px; font-weight:600;}
  .tag.entry{background:rgba(61,220,151,.12); color:var(--green);}
  .tag.exit{background:rgba(255,92,122,.12); color:var(--red);}
  .tag.register, .tag.registration_scan{background:rgba(255,200,87,.12); color:var(--yellow);}
  .tag.registration_confirm{background:rgba(91,140,255,.14); color:var(--accent);}
  .scroll{max-height:420px; overflow-y:auto;}
  .dot{display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px;}
  .dot.in{background:var(--green);}
  .dot.out{background:var(--muted);}
  .empty{color:var(--muted); font-size:13px; padding:14px 0; text-align:center;}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <h1>Админ-панель <span>контроля доступа</span></h1>
    <div style="display:flex; align-items:center; gap:16px;">
      <a class="pubLink" href="/" target="_blank">Публичная страница →</a>
      <button class="btn" id="toggleBtn">Загрузка...</button>
    </div>
  </div>

  <div class="stats">
    <div class="stat-card">
      <div class="stat-label">Всего событий</div>
      <div class="stat-value" id="sTotalEvents">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Людей внутри</div>
      <div class="stat-value green" id="sInside">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Входов</div>
      <div class="stat-value blue" id="sEntries">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Выходов</div>
      <div class="stat-value red" id="sExits">—</div>
    </div>
  </div>

  <div class="columns">
    <div class="panel">
      <h2>Лента событий <span class="badge open" id="regBadgeAdmin">—</span></h2>
      <div class="scroll">
        <table>
          <thead><tr><th>Время</th><th>Действие</th><th>UID</th></tr></thead>
          <tbody id="eventsBody"></tbody>
        </table>
        <div class="empty" id="eventsEmpty" style="display:none;">Событий пока нет</div>
      </div>
    </div>

    <div class="panel">
      <h2>Пользователи</h2>
      <div class="scroll">
        <table>
          <thead><tr><th>UID</th><th>Имя</th><th>Статус</th></tr></thead>
          <tbody id="usersBody"></tbody>
        </table>
        <div class="empty" id="usersEmpty" style="display:none;">Пользователей пока нет</div>
      </div>
    </div>
  </div>
</div>

<script>
const actionsRu = {
  entry: 'Вход', exit: 'Выход', register: 'Авторегистрация',
  registration_scan: 'Скан для регистрации',
  registration_confirm: 'Регистрация подтверждена'
};

async function refreshAdmin() {
  try {
    const [dataRes, regRes] = await Promise.all([
      fetch('/api/get-users'), fetch('/api/registration-status')
    ]);
    const data = await dataRes.json();
    const reg = await regRes.json();

    document.getElementById('sTotalEvents').textContent = data.stats.total_events;
    document.getElementById('sInside').textContent = data.stats.inside_count;
    document.getElementById('sEntries').textContent = data.stats.entries;
    document.getElementById('sExits').textContent = data.stats.exits;

    const badge = document.getElementById('regBadgeAdmin');
    badge.className = 'badge ' + (reg.registration_open ? 'open' : 'closed');
    badge.textContent = reg.registration_open
      ? ('Регистрация открыта' + (reg.pending_uid ? (' · ждём: ' + reg.pending_uid) : ''))
      : 'Регистрация закрыта';

    const toggleBtn = document.getElementById('toggleBtn');
    toggleBtn.textContent = reg.registration_open ? 'Закрыть регистрацию' : 'Открыть регистрацию';
    toggleBtn.className = 'btn' + (reg.registration_open ? ' danger' : '');

    const eventsBody = document.getElementById('eventsBody');
    eventsBody.innerHTML = '';
    document.getElementById('eventsEmpty').style.display = data.events.length ? 'none' : 'block';
    data.events.forEach(ev => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${ev.timestamp}</td>
        <td><span class="tag ${ev.action}">${actionsRu[ev.action] || ev.action}</span></td>
        <td class="uid">${ev.uid}</td>`;
      eventsBody.appendChild(tr);
    });

    const usersBody = document.getElementById('usersBody');
    usersBody.innerHTML = '';
    document.getElementById('usersEmpty').style.display = data.users.length ? 'none' : 'block';
    data.users.forEach(u => {
      const tr = document.createElement('tr');
      const fio = (u.name + ' ' + u.surname).trim() || '—';
      tr.innerHTML = `<td class="uid">${u.uid}</td>
        <td>${fio}</td>
        <td><span class="dot ${u.is_inside ? 'in' : 'out'}"></span>${u.is_inside ? 'Внутри' : 'Снаружи'}</td>`;
      usersBody.appendChild(tr);
    });
  } catch (e) { /* тихо игнорируем сетевые сбои при поллинге */ }
}

document.getElementById('toggleBtn').addEventListener('click', async () => {
  await fetch('/toggle-registration', { method: 'POST' });
  refreshAdmin();
});

refreshAdmin();
setInterval(refreshAdmin, 2000);
</script>
</body>
</html>
"""


# ============================================================
#  РОУТЫ СТРАНИЦ
# ============================================================
@app.route("/")
def index():
    return render_template_string(PUBLIC_HTML)


@app.route("/admin")
def admin():
    return render_template_string(ADMIN_HTML)


# ============================================================
#  ЗАПУСК
# ============================================================
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
