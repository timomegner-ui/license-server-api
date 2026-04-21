from flask import Flask, request, jsonify, render_template_string
import os
import json
import uuid

app = Flask(__name__)

DATA_FILE = "keys.json"


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


@app.route("/")
def home():
    return "License Server läuft!"


# ===============================
# KEY PRÜFUNG (für deine App)
# ===============================
@app.route("/check_key")
def check_key():
    key = request.args.get("key", "").strip()
    keys = lade_keys()

    if not key:
        return jsonify({"valid": False, "reason": "no_key"})

    eintrag = keys.get(key)

    if not eintrag:
        return jsonify({"valid": False, "reason": "not_found"})

    if not eintrag.get("active", False):
        return jsonify({"valid": False, "reason": "inactive"})

    return jsonify({"valid": True})


# ===============================
# DIGISTORE WEBHOOK
# ===============================
@app.route("/digistore_webhook", methods=["POST", "GET"])
def digistore_webhook():
    print("METHOD:", request.method, flush=True)
    print("FORM:", request.form.to_dict(), flush=True)
    print("ARGS:", request.args.to_dict(), flush=True)

    data = lese_request_daten()
    if not data:
        data = request.args.to_dict()

    print("DIGISTORE DATA:", data, flush=True)

    keys = lade_keys()

    event = str(
        data.get("event")
        or data.get("type")
        or data.get("status")
        or ""
    ).strip().lower()

    order_id = str(data.get("order_id", "")).strip()
    buyer_email = str(
        data.get("buyer_email")
        or data.get("email")
        or ""
    ).strip().lower()

    product_id = str(data.get("product_id", "")).strip()
    lizenz_key = hole_key_aus_daten(data)

    refund_events = [
        "refund", "chargeback", "cancel", "cancellation",
        "on_refund", "on_chargeback"
    ]

    # 🔴 REFUND
    if event in refund_events:
        gefunden_key = None

        if lizenz_key and lizenz_key in keys:
            gefunden_key = lizenz_key
        elif order_id:
            for k, v in keys.items():
                if str(v.get("order_id")) == order_id:
                    gefunden_key = k
                    break
        elif buyer_email:
            for k, v in keys.items():
                if str(v.get("buyer_email")).lower() == buyer_email:
                    gefunden_key = k
                    break

        if gefunden_key:
            keys[gefunden_key]["active"] = False
            speichere_keys(keys)

        return jsonify({
            "status": "success",
            "key": "Lizenz deaktiviert",
            "headline": "Lizenzstatus",
            "show_on": ["receipt_page", "order_confirmation_email"]
        }), 200

    # 🟢 KAUF
    if not lizenz_key:
        lizenz_key = "TM-" + str(uuid.uuid4())[:12].upper()

    keys[lizenz_key] = {
        "active": True,
        "buyer_email": buyer_email,
        "order_id": order_id,
        "product_id": product_id
    }

    speichere_keys(keys)

    return jsonify({
        "status": "success",
        "key": lizenz_key,
        "headline": "Dein Lizenzschlüssel",
        "show_on": ["receipt_page", "order_confirmation_email"]
    }), 200


# ===============================
# KEY MANUELL DEAKTIVIEREN
# ===============================
@app.route("/deactivate_key", methods=["POST"])
def deactivate_key():
    data = lese_request_daten()
    key = hole_key_aus_daten(data)

    keys = lade_keys()

    if key in keys:
        keys[key]["active"] = False
        speichere_keys(keys)

    return jsonify({"ok": True})


# ===============================
# LICENSE PAGE (optional)
# ===============================
@app.route("/license")
def license_page():
    email = request.args.get("buyer_email", "").lower()

    keys = lade_keys()

    for key, data in keys.items():
        if data.get("buyer_email", "").lower() == email:
            return f"""
            <h1>Dein Lizenzschlüssel:</h1>
            <h2>{key}</h2>
            """

    return "<h1>Kein Key gefunden</h1>"


# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
