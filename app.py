from flask import Flask, request, jsonify
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

    print("DIGISTORE DATA:", data, flush=True)

    lizenz_key = hole_key_aus_daten(data)
    event = str(data.get("event", "")).strip().lower()
    order_id = str(data.get("order_id", "")).strip()
    buyer_email = str(data.get("buyer_email", "")).strip().lower()
    product_id = str(data.get("product_id", "")).strip()

    # wenn Digistore keinen Key liefert -> selbst erzeugen
    if not lizenz_key and event not in [
        "refund", "chargeback", "cancel", "cancellation",
        "on_refund", "on_chargeback"
    ]:
        lizenz_key = "TM-" + str(uuid.uuid4())[:12].upper()

    # Rückgabe / Sperrung
    if event in [
        "refund", "chargeback", "cancel", "cancellation",
        "on_refund", "on_chargeback"
    ]:
        gefunden = False

        if lizenz_key and lizenz_key in keys:
            keys[lizenz_key]["active"] = False
            keys[lizenz_key]["event"] = event
            gefunden = True

        elif order_id:
            for k, v in keys.items():
                if str(v.get("order_id", "")).strip() == order_id:
                    keys[k]["active"] = False
                    keys[k]["event"] = event
                    lizenz_key = k
                    gefunden = True
                    break

        speichere_keys(keys)

        return jsonify({
            "ok": True,
            "action": "deactivated" if gefunden else "refund_received_but_key_not_found",
            "license_key": lizenz_key,
            "event": event
        }), 200

    # Kauf / Aktivierung
    if lizenz_key:
        keys[lizenz_key] = {
            "active": True,
            "source": "digistore24",
            "buyer_email": buyer_email,
            "order_id": order_id,
            "product_id": product_id,
            "event": event or "purchase"
        }

        speichere_keys(keys)

        return jsonify({
            "ok": True,
            "action": "stored",
            "license_key": lizenz_key,
            "event": event or "purchase"
        }), 200

    return jsonify({
        "ok": True,
        "action": "received_but_no_key_stored",
        "event": event,
        "data": data
    }), 200


@app.route("/license")
def license_page():
    order_id = request.args.get("order_id", "").strip()
    email = request.args.get("email", "").strip().lower()

    keys = lade_keys()

    gefunden_key = None
    gefunden_eintrag = None

    for k, v in keys.items():
        if order_id and str(v.get("order_id", "")).strip() == order_id:
            gefunden_key = k
            gefunden_eintrag = v
            break

        if email and str(v.get("buyer_email", "")).strip().lower() == email:
            gefunden_key = k
            gefunden_eintrag = v
            break

    if not gefunden_key:
        return """
        <html>
            <head>
                <meta charset="utf-8">
                <title>Lizenz nicht gefunden</title>
            </head>
            <body style="font-family:Arial;background:#111;color:white;padding:40px;">
                <h1>Lizenz nicht gefunden</h1>
                <p>Es konnte noch kein Lizenzschlüssel zugeordnet werden.</p>
                <p>Bitte prüfe Bestellnummer oder E-Mail-Adresse.</p>
            </body>
        </html>
        """

    status = "AKTIV" if gefunden_eintrag.get("active", False) else "GESPERRT"

    return f"""
    <html>
        <head>
            <meta charset="utf-8">
            <title>Dein Lizenzschlüssel</title>
        </head>
        <body style="font-family:Arial;background:#111;color:white;padding:40px;">
            <h1>Dein Lizenzschlüssel</h1>
            <p><strong>Status:</strong> {status}</p>
            <p><strong>Lizenzschlüssel:</strong></p>
            <div style="font-size:28px;padding:20px;background:#1c1c1c;border:1px solid #444;border-radius:10px;display:inline-block;">
                {gefunden_key}
            </div>
            <p style="margin-top:30px;">Bitte kopiere diesen Schlüssel und füge ihn in deine App ein.</p>
        </body>
    </html>
    """


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
