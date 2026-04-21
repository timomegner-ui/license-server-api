from flask import Flask, request, jsonify
import os
import json

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

    return jsonify({
        "valid": True,
        "source": eintrag.get("source", "unknown"),
        "event": eintrag.get("event", "")
    })


@app.route("/digistore_webhook", methods=["POST"])
def digistore_webhook():
    data = lese_request_daten()
    keys = lade_keys()

    lizenz_key = hole_key_aus_daten(data)
    event = str(data.get("event", "")).strip().lower()

    if not lizenz_key:
        return jsonify({
            "ok": False,
            "error": "Kein license_key empfangen"
        }), 400

    # Rückgabe / Sperrung
    if event in ["refund", "chargeback", "cancel", "cancellation", "on_refund", "on_chargeback"]:
        if lizenz_key in keys:
            keys[lizenz_key]["active"] = False
            keys[lizenz_key]["event"] = event
            keys[lizenz_key]["buyer_email"] = data.get("buyer_email", keys[lizenz_key].get("buyer_email", ""))
            keys[lizenz_key]["order_id"] = data.get("order_id", keys[lizenz_key].get("order_id", ""))
            keys[lizenz_key]["product_id"] = data.get("product_id", keys[lizenz_key].get("product_id", ""))
        else:
            keys[lizenz_key] = {
                "active": False,
                "source": "digistore24",
                "buyer_email": data.get("buyer_email", ""),
                "order_id": data.get("order_id", ""),
                "product_id": data.get("product_id", ""),
                "event": event
            }

        speichere_keys(keys)

        return jsonify({
            "ok": True,
            "action": "deactivated",
            "license_key": lizenz_key
        })

    # Kauf / Aktivierung
    keys[lizenz_key] = {
        "active": True,
        "source": "digistore24",
        "buyer_email": data.get("buyer_email", ""),
        "order_id": data.get("order_id", ""),
        "product_id": data.get("product_id", ""),
        "event": event or "purchase"
    }

    speichere_keys(keys)

    return jsonify({
        "ok": True,
        "action": "stored",
        "license_key": lizenz_key
    })


@app.route("/deactivate_key", methods=["POST"])
def deactivate_key():
    data = lese_request_daten()
    lizenz_key = hole_key_aus_daten(data)

    if not lizenz_key:
        return jsonify({
            "ok": False,
            "error": "Kein license_key empfangen"
        }), 400

    keys = lade_keys()

    if lizenz_key not in keys:
        return jsonify({
            "ok": False,
            "error": "Key nicht gefunden"
        }), 404

    keys[lizenz_key]["active"] = False
    keys[lizenz_key]["event"] = "deactivated"

    speichere_keys(keys)

    return jsonify({
        "ok": True,
        "deactivated_key": lizenz_key
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
