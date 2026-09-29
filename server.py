# ==================================================================
# RFID Access Control — сервер (Python / Flask)
#
# Архитектура: 2 ESP.
#   Главный ESP, классический ESP32 (2 ридера):
#     reader=1 ВХОД — только вход, всегда
#     reader=2 ВЫХОД — только выход, всегда
#   Второй ESP, ESP32-S3 (1 ридер):
#     reader=3 РЕГИСТРАЦИЯ — только скан для регистрации
#
# Правила:
#   Вход — только если карта снаружи (иначе 409 DENY_ALREADY_INSIDE).
#   Выход — только если карта внутри (иначе 409 DENY_NOT_INSIDE).
#   Скан регистрации — только при открытой регистрации
#     (иначе 409 DENY_REG_CLOSED). Вход/выход этот ридер не делает.
#   Повторный скан той же карты режется кулдауном 3 сек (антиспам,
#     пока карту держат на ридере).
#
# Админка: /admin (вся работа здесь: мониторинг, регистрация,
#   открытие/закрытие регистрации, полный сброс с двойным
#   подтверждением). Корень / редиректит на /admin.
#
# Деплой (Render): Procfile -> gunicorn server:app --workers 1
#   (--workers 1 обязателен: состояние в памяти процесса).
# ==================================================================

import json
import os
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
DB_FILE = os.path.join(BASE_DIR, "db.json")

app = Flask(__name__, static_folder=None)
db_lock = threading.Lock()

SCAN_COOLDOWN_SEC = 3.0
MAX_EVENTS = 500

# (reader, uid) -> время последнего принятого скана (защита от спама)
_last_scan = {}

state = {
    "registration_open": False,
    "pending_uid": None,
    "users": {},   # uid -> {uid, name, surname, registered, is_inside, created_at}
    "events": [],  # [{timestamp, action, uid, reader}], новые в начале
}


# ------------------------- persistence -------------------------
def load_state():
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            for k in ("registration_open", "pending_uid", "users", "events"):
                if k in parsed:
                    state[k] = parsed[k]
            print("OK: state loaded from db.json")
    except Exception as e:
        print(f"WARN: load db.json failed: {e}")


def save_state():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"WARN: save db.json failed: {e}")


load_state()


# ------------------------- helpers -------------------------
def now_str():
    return datetime.now().strftime("%d.%m.%y, %H:%M:%S")


def push_event(action, uid, reader=None):
    state["events"].insert(0, {
        "timestamp": now_str(), "action": action, "uid": uid, "reader": reader,
    })
    if len(state["events"]) > MAX_EVENTS:
        del state["events"][MAX_EVENTS:]


def get_stats():
    users = list(state["users"].values())
    return {
        "total_events": len(state["events"]),
        "inside_count": sum(1 for u in users if u.get("is_inside")),
        "entries": sum(1 for e in state["events"] if e["action"] == "entry"),
        "exits": sum(1 for e in state["events"] if e["action"] == "exit"),
    }


def is_duplicate_scan(reader, uid):
    key = (reader, uid)
    now = time.monotonic()
    last = _last_scan.get(key, 0)
    if now - last < SCAN_COOLDOWN_SEC:
        return True
    _last_scan[key] = now
    return False


# ------------------------- API -------------------------
@app.get("/api/registration-status")
def registration_status():
    return jsonify({
        "registration_open": state["registration_open"],
        "pending_uid": state["pending_uid"],
    })


@app.get("/api/public-data")
def public_data():
    last = state["events"][0] if state["events"] else None
    return jsonify({
        "inside_count": get_stats()["inside_count"],
        "last_event_time": last["timestamp"] if last else None,
        "last_event_action": last["action"] if last else None,
        "last_event_uid": last["uid"] if last else None,
        "last_event_reader": last.get("reader") if last else None,
    })


@app.get("/api/get-users")
def get_users():
    return jsonify({
        "stats": get_stats(),
        "events": state["events"],
        "users": list(state["users"].values()),
    })


@app.post("/toggle-registration")
def toggle_registration():
    with db_lock:
        state["registration_open"] = not state["registration_open"]
        if not state["registration_open"]:
            state["pending_uid"] = None
        save_state()
    return jsonify({"status": "ok", "registration_open": state["registration_open"]})


@app.post("/confirm-registration")
def confirm_registration():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    surname = (body.get("surname") or "").strip()

    with db_lock:
        if not state["registration_open"]:
            return jsonify({"status": "error", "message": "Регистрация закрыта"}), 400
        if not state["pending_uid"]:
            return jsonify({"status": "error", "message": "Сначала приложите карту к ридеру №3"}), 400
        if not name or not surname:
            return jsonify({"status": "error", "message": "Заполните имя и фамилию"}), 400

        uid = state["pending_uid"]
        state["users"][uid] = {
            "uid": uid,
            "name": name,
            "surname": surname,
            "registered": True,
            "is_inside": False,  # регистрация НЕ = вход
            "created_at": datetime.now().isoformat(),
        }
        push_event("registration_confirm", uid, None)
        state["pending_uid"] = None
        save_state()
    return jsonify({"status": "ok", "uid": uid})


@app.post("/reset-all")
def reset_all():
    """Полная очистка: пользователи, события, pending-карта, регистрация закрыта."""
    with db_lock:
        state["users"] = {}
        state["events"] = []
        state["pending_uid"] = None
        state["registration_open"] = False
        _last_scan.clear()
        save_state()
        print("RESET-ALL: all data cleared via admin")
    return jsonify({"status": "ok", "message": "Всё очищено"})


# ------------------------- ESP32 -------------------------
@app.get("/rfid")
def rfid():
    reader = request.args.get("reader", "")
    uid = request.args.get("uid", "").upper()

    if not uid:
        return "ERROR: no uid", 400
    if reader not in ("1", "2", "3"):
        return "ERROR: unknown reader", 400

    with db_lock:
        # Ридер №3 (второй ESP) — ТОЛЬКО скан регистрации
        if reader == "3":
            if not state["registration_open"]:
                return "DENY_REG_CLOSED", 409
            key = ("reg", uid)
            now = time.monotonic()
            if state["pending_uid"] == uid and (now - _last_scan.get(key, 0) < SCAN_COOLDOWN_SEC):
                return "OK: registration pending, fill the form"
            _last_scan[key] = now
            state["pending_uid"] = uid
            push_event("registration_scan", uid, reader)
            save_state()
            print(f"REG-SCAN (reader=3): {uid}")
            return "OK: registration pending, fill the form"

        # Ридеры №1/№2 (главный ESP) — ТОЛЬКО вход/выход.
        # Работают всегда, даже при открытой регистрации.
        if is_duplicate_scan(reader, uid):
            return "OK: duplicate ignored"

        # №1 — ВХОД, только если карта снаружи
        if reader == "1":
            user = state["users"].get(uid)
            if not user:
                return "ERROR: card not registered", 404
            if user.get("is_inside"):
                push_event("entry_denied", uid, reader)
                save_state()
                print(f"ENTRY DENIED (already inside): {uid}")
                return "DENY_ALREADY_INSIDE", 409
            user["is_inside"] = True
            push_event("entry", uid, reader)
            save_state()
            print(f"ENTRY: {uid} ({user['name']} {user['surname']})")
            return "OK: entry"

        # №2 — ВЫХОД, только если карта внутри
        user = state["users"].get(uid)
        if not user:
            return "ERROR: card not registered", 404
        if not user.get("is_inside"):
            push_event("exit_denied", uid, reader)
            save_state()
            print(f"EXIT DENIED (not inside): {uid}")
            return "DENY_NOT_INSIDE", 409
        user["is_inside"] = False
        push_event("exit", uid, reader)
        save_state()
        print(f"EXIT: {uid} ({user['name']} {user['surname']})")
        return "OK: exit"


# ------------------------- static -------------------------
@app.get("/")
def serve_index():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.get("/admin")
def serve_admin():
    return send_from_directory(PUBLIC_DIR, "admin.html")


@app.get("/<path:filename>")
def serve_static(filename):
    return send_from_directory(PUBLIC_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
