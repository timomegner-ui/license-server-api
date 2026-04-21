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

    # Refund / Chargeback / Sperrung
    if event in refund_events:
        gefunden_key = None

        # 1. erst direkt über license_key
        if lizenz_key and lizenz_key in keys:
            gefunden_key = lizenz_key

        # 2. sonst über order_id
        elif order_id:
            for k, v in keys.items():
                if str(v.get("order_id", "")).strip() == order_id:
                    gefunden_key = k
                    break

        # 3. sonst über buyer_email
        elif buyer_email:
            for k, v in keys.items():
                if str(v.get("buyer_email", "")).strip().lower() == buyer_email:
                    gefunden_key = k
                    break

        if gefunden_key:
            keys[gefunden_key]["active"] = False
            keys[gefunden_key]["event"] = event
            speichere_keys(keys)

            return jsonify({
                "status": "success",
                "key": "Lizenzstatus aktualisiert.",
                "data": [],
                "headline": "Lizenzstatus",
                "show_on": ["receipt_page", "order_confirmation_email"]
            }), 200

        return jsonify({
            "status": "success",
            "key": "Keine passende Lizenz gefunden.",
            "data": [],
            "headline": "Lizenzstatus",
            "show_on": ["receipt_page", "order_confirmation_email"]
        }), 200

    # Kauf / Aktivierung
    if not lizenz_key:
        lizenz_key = "TM-" + str(uuid.uuid4())[:12].upper()

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
        "status": "success",
        "key": f"Lizenzschlüssel: {lizenz_key}",
        "data": [],
        "headline": "Ihr Lizenzschlüssel",
        "show_on": ["receipt_page", "order_confirmation_email"]
    }), 200


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


@app.route("/license")
def license_page():
    order_id = request.args.get("order_id", "").strip()
    buyer_email = request.args.get("buyer_email", "").strip().lower()
    email = request.args.get("email", "").strip().lower()

    such_email = buyer_email or email
    keys = lade_keys()

    gefunden_key = None
    gefunden_eintrag = None

    for key, eintrag in keys.items():
        if order_id and str(eintrag.get("order_id", "")).strip() == order_id:
            gefunden_key = key
            gefunden_eintrag = eintrag
            break

        if such_email and str(eintrag.get("buyer_email", "")).strip().lower() == such_email:
            gefunden_key = key
            gefunden_eintrag = eintrag
            break

    if not gefunden_key:
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="de">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Lizenz nicht gefunden</title>
            <style>
                body{
                    margin:0;
                    font-family:Arial, sans-serif;
                    background:#0e0e11;
                    color:white;
                    padding:40px;
                }
                .box{
                    max-width:900px;
                    margin:0 auto;
                }
                h1{
                    font-size:64px;
                    margin-bottom:30px;
                }
                p{
                    font-size:28px;
                    line-height:1.5;
                    color:#d6d6d6;
                }
            </style>
        </head>
        <body>
            <div class="box">
                <h1>Kein Lizenzschlüssel gefunden</h1>
                <p>Wir konnten noch keinen passenden Schlüssel zu deiner Bestellung finden.</p>
                <p>Bitte warte kurz und lade die Seite neu oder kontaktiere den Support.</p>
            </div>
        </body>
        </html>
        """)

    status = "AKTIV" if gefunden_eintrag.get("active", False) else "GESPERRT"

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="de">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dein Lizenzschlüssel</title>
        <style>
            body{
                margin:0;
                font-family:Arial, sans-serif;
                background:#0b0b0e;
                color:white;
                padding:40px;
            }
            .wrap{
                max-width:1000px;
                margin:0 auto;
            }
            h1{
                font-size:72px;
                margin:0 0 40px 0;
                font-weight:700;
            }
            .status{
                font-size:32px;
                margin-bottom:30px;
            }
            .label{
                font-size:30px;
                font-weight:700;
                margin-bottom:20px;
            }
            .keybox{
                display:flex;
                align-items:center;
                justify-content:space-between;
                gap:20px;
                background:#171717;
                border:2px solid #3a3a3a;
                border-radius:24px;
                padding:35px 40px;
                margin:20px 0 40px 0;
                max-width:900px;
            }
            .keytext{
                font-size:64px;
                font-weight:700;
                letter-spacing:1px;
                word-break:break-all;
            }
            .copybtn{
                border:none;
                border-radius:14px;
                background:#2b56ff;
                color:white;
                font-size:22px;
                padding:18px 24px;
                cursor:pointer;
                min-width:150px;
            }
            .copybtn:hover{
                background:#1f46e6;
            }
            .hint{
                font-size:28px;
                line-height:1.5;
                color:#e5e5e5;
            }
            .small{
                margin-top:25px;
                color:#9f9f9f;
                font-size:20px;
            }
            @media (max-width: 900px){
                h1{font-size:44px;}
                .status{font-size:24px;}
                .label{font-size:24px;}
                .keybox{
                    flex-direction:column;
                    align-items:flex-start;
                    padding:24px;
                }
                .keytext{font-size:34px;}
                .copybtn{width:100%;}
                .hint{font-size:22px;}
            }
        </style>
    </head>
    <body>
        <div class="wrap">
            <h1>Dein Lizenzschlüssel</h1>

            <div class="status"><strong>Status:</strong> {{ status }}</div>

            <div class="label">Lizenzschlüssel:</div>

            <div class="keybox">
                <div class="keytext" id="licenseKey">{{ key }}</div>
                <button class="copybtn" onclick="copyKey()">Kopieren</button>
            </div>

            <div class="hint">
                Bitte kopiere diesen Schlüssel und füge ihn in deine App ein.
            </div>

            <div class="small" id="copyInfo"></div>
        </div>

        <script>
            function copyKey() {
                const key = document.getElementById("licenseKey").innerText;
                navigator.clipboard.writeText(key).then(function() {
                    document.getElementById("copyInfo").innerText = "Lizenzschlüssel wurde kopiert.";
                }).catch(function() {
                    document.getElementById("copyInfo").innerText = "Kopieren fehlgeschlagen. Bitte manuell kopieren.";
                });
            }
        </script>
    </body>
    </html>
    """, key=gefunden_key, status=status)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
