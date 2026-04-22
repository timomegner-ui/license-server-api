from flask import Flask, request, jsonify, render_template_string
import os
import json
import uuid

app = Flask(__name__)

# ===============================
# WICHTIG: Render Disk Pfad
# ===============================
DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(DATA_DIR, "keys.json")

RESET_SECRET = "MEIN_GEHEIMER_RESET_KEY_123"

ADMIN_USER = "admin"
ADMIN_PASSWORD = "DEIN_SICHERES_PASSWORT_123"


# ===============================
# FILE HANDLING
# ===============================
def lade_keys():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def speichere_keys(keys):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2, ensure_ascii=False)


def lese_request_daten():
    data = request.form.to_dict()
    if not data:
        try:
            data = request.get_json(force=True, silent=True) or {}
        except:
            data = {}
    return data


def hole_key_aus_daten(data):
    return (
        data.get("license_key")
        or data.get("licence_key")
        or data.get("key")
        or ""
    ).strip()


def admin_auth_ok():
    user = request.authorization.username if request.authorization else ""
    password = request.authorization.password if request.authorization else ""
    return user == ADMIN_USER and password == ADMIN_PASSWORD


# ===============================
# ROOT
# ===============================
@app.route("/")
def home():
    return "License Server läuft!"


# ===============================
# KEY CHECK
# ===============================
@app.route("/check_key")
def check_key():
    key = request.args.get("key", "").strip()
    keys = lade_keys()

    if not key:
        return jsonify({"valid": False})

    eintrag = keys.get(key)

    if not eintrag:
        return jsonify({"valid": False})

    if not eintrag.get("active", False):
        return jsonify({"valid": False})

    return jsonify({"valid": True})


# ===============================
# DIGISTORE WEBHOOK
# ===============================
@app.route("/digistore_webhook", methods=["POST", "GET"])
def digistore_webhook():
    data = lese_request_daten()
    if not data:
        data = request.args.to_dict()

    keys = lade_keys()

    event = str(data.get("event") or "").lower()
    order_id = str(data.get("order_id", "")).strip()
    buyer_email = str(data.get("buyer_email", "")).strip().lower()
    product_id = str(data.get("product_id", "")).strip()
    lizenz_key = hole_key_aus_daten(data)

    # REFUND
    if event in ["refund", "chargeback"]:
        for k, v in keys.items():
            if v.get("order_id") == order_id:
                keys[k]["active"] = False
                speichere_keys(keys)
                return jsonify({"status": "deactivated"})
        return jsonify({"status": "not_found"})

    # KAUF
    if not lizenz_key:
        lizenz_key = "TM-" + str(uuid.uuid4())[:12].upper()

    keys[lizenz_key] = {
        "active": True,
        "buyer_email": buyer_email,
        "order_id": order_id,
        "product_id": product_id,
        "event": event or "purchase"
    }

    speichere_keys(keys)

    return jsonify({"status": "success", "key": lizenz_key})


# ===============================
# FREE KEY
# ===============================
@app.route("/create_free_key")
def create_free_key():
    secret = request.args.get("secret")

    if secret != RESET_SECRET:
        return jsonify({"error": "unauthorized"}), 403

    email = request.args.get("email", "free").lower()
    keys = lade_keys()

    for k, v in keys.items():
        if v.get("buyer_email") == email:
            return jsonify({"key": k})

    key = "TM-" + str(uuid.uuid4())[:12].upper()

    keys[key] = {
        "active": True,
        "buyer_email": email,
        "event": "free"
    }

    speichere_keys(keys)

    return jsonify({"key": key})


# ===============================
# ADMIN PANEL
# ===============================
@app.route("/admin")
def admin_panel():
    if not admin_auth_ok():
        return ("Login erforderlich", 401,
                {"WWW-Authenticate": 'Basic realm="Login"'})

    keys = lade_keys()

    rows = ""
    for key, data in keys.items():
        status = "AKTIV" if data.get("active") else "GESPERRT"

        rows += f"""
        <tr>
            <td>{key}</td>
            <td>{status}</td>
            <td>{data.get("buyer_email","")}</td>
            <td>
                <a href="/enable?key={key}">Aktivieren</a> |
                <a href="/disable?key={key}">Deaktivieren</a> |
                <a href="/delete?key={key}">Löschen</a>
            </td>
        </tr>
        """

    return f"""
    <h1>Admin Panel</h1>
    <table border=1>
    <tr><th>Key</th><th>Status</th><th>Email</th><th>Aktion</th></tr>
    {rows}
    </table>
    """


# ===============================
# ADMIN ACTIONS
# ===============================
@app.route("/enable")
def enable():
    key = request.args.get("key")
    keys = lade_keys()

    if key in keys:
        keys[key]["active"] = True
        speichere_keys(keys)

    return "OK"


@app.route("/disable")
def disable():
    key = request.args.get("key")
    keys = lade_keys()

    if key in keys:
        keys[key]["active"] = False
        speichere_keys(keys)

    return "OK"


@app.route("/delete")
def delete():
    key = request.args.get("key")
    keys = lade_keys()

    if key in keys:
        del keys[key]
        speichere_keys(keys)

    return "OK"


# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
