from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import datetime
import os

app = Flask(__name__)
CORS(app)

DB_FILE = 'rfid_logs.db'

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE card_status (
        uid TEXT PRIMARY KEY,
        is_inside INTEGER NOT NULL
    )''')
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
pending_uid = None

# ==================== API ====================
@app.route('/rfid', methods=['GET'])
def handle_rfid():
    global pending_uid, registration_open
    
    reader = request.args.get('reader')
    uid = request.args.get('uid')
    action = request.args.get('action')

    if not reader or not uid:
        return jsonify({"error": "Missing parameters"}), 400

    print(f"📥 reader={reader}, uid={uid}, action={action}")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ===== РЕГИСТРАЦИЯ =====
    if action == "REGISTER" or reader == "3":
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
        return jsonify({"status": "waiting_for_name", "uid": uid, "message": "Ожидайте ввода имени"})

    # ===== ВХОД / ВЫХОД =====
    c.execute("SELECT name, surname, is_inside FROM users WHERE uid = ?", (uid,))
    user = c.fetchone()
    
    if not user:
        c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('unregistered_attempt', ?, ?)", (uid, now))
        conn.commit()
        conn.close()
        return jsonify({"status": "not_registered", "message": "Карта не зарегистрирована"}), 403

    name, surname, is_inside = user

    if reader == "1":  # ВХОД
        if is_inside:
            c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('blocked_enter', ?, ?)", (uid, now))
            message = "already_inside"
        else:
            c.execute("UPDATE users SET is_inside = 1 WHERE uid = ?", (uid,))
            c.execute("REPLACE INTO card_status (uid, is_inside) VALUES (?, 1)", (uid,))
            c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('enter', ?, ?)", (uid, now))
            message = "enter_ok"

    elif reader == "2":  # ВЫХОД
        if not is_inside:
            c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('blocked_exit', ?, ?)", (uid, now))
            message = "already_outside"
        else:
            c.execute("UPDATE users SET is_inside = 0 WHERE uid = ?", (uid,))
            c.execute("REPLACE INTO card_status (uid, is_inside) VALUES (?, 0)", (uid,))
            c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('exit', ?, ?)", (uid, now))
            message = "exit_ok"

    else:
        conn.close()
        return jsonify({"error": "Invalid reader"}), 400

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "message": message, "name": name, "surname": surname})

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
        return jsonify({"status": "error", "message": "UID не совпадает"}), 400
        
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("SELECT uid FROM users WHERE uid = ?", (uid,))
    if c.fetchone():
        pending_uid = None
        conn.close()
        return jsonify({"status": "error", "message": "Карта уже зарегистрирована"}), 400
        
    c.execute("INSERT INTO users (uid, name, surname, is_inside) VALUES (?, ?, ?, 0)", (uid, name, surname))
    c.execute("REPLACE INTO card_status (uid, is_inside) VALUES (?, 0)", (uid,))
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO events (action, uid, timestamp) VALUES ('register', ?, ?)", (uid, now))
    conn.commit()
    conn.close()
    
    pending_uid = None
    return jsonify({"status": "ok", "message": "Пользователь зарегистрирован"})

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

@app.route('/')
def home():
    return "RFID Server is running! Use /admin for admin panel."

@app.route('/admin')
def admin():
    return "Admin panel - coming soon"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
