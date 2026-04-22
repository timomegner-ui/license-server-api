from flask import Flask, request, jsonify, render_template_string
import os
import json
import uuid

app = Flask(__name__)

# ===============================
# PERSISTENTER SPEICHER AUF RENDER DISK
# ===============================
if os.path.exists("/Data"):
    DATA_DIR = "/Data"
elif os.path.exists("/data"):
    DATA_DIR = "/data"
else:
    DATA_DIR = "."

print("AKTIVES DATA_DIR:", DATA_DIR, flush=True)

DATA_FILE = os.path.join(DATA_DIR, "keys.json")
print("DATA_FILE:", DATA_FILE, flush=True)

RESET_SECRET = "MEIN_GEHEIMER_RESET_KEY_123"

ADMIN_USER = "admin"
ADMIN_PASSWORD = "DEIN_SICHERES_PASSWORT_123"


def lade_keys():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def speichere_keys(keys):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2, ensure_ascii=False)


def lese_request_daten():
    data = request.form.to_dict()
    if not data:
        try:
            data = request.get_json(force=True, silent=True) or {}
        except Exception:
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


@app.route("/")
def home():
    return "License Server läuft!"


# ===============================
# KEY PRÜFUNG (für deine App) + MACHINE ID BINDING
# ===============================
@app.route("/check_key")
def check_key():
    key = request.args.get("key", "").strip()
    machine_id = request.args.get("machine_id", "").strip()

    keys = lade_keys()

    if not key:
        return jsonify({"valid": False, "reason": "no_key"})

    eintrag = keys.get(key)

    if not eintrag:
        return jsonify({"valid": False, "reason": "not_found"})

    if not eintrag.get("active", False):
        return jsonify({"valid": False, "reason": "inactive"})

    gespeicherte_machine = str(eintrag.get("machine_id", "")).strip()

    # Erster gültiger Login -> Gerät merken
    if not gespeicherte_machine and machine_id:
        eintrag["machine_id"] = machine_id
        keys[key] = eintrag
        speichere_keys(keys)
        return jsonify({"valid": True, "reason": "bound_to_device"})

    # Wenn schon ein Gerät gespeichert ist, muss es übereinstimmen
    if gespeicherte_machine:
        if not machine_id:
            return jsonify({"valid": False, "reason": "missing_machine_id"})
        if machine_id != gespeicherte_machine:
            return jsonify({"valid": False, "reason": "wrong_device"})

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

    # Refund / Chargeback / Sperrung
    if event in refund_events:
        gefunden_key = None

        if lizenz_key and lizenz_key in keys:
            gefunden_key = lizenz_key
        elif order_id:
            for k, v in keys.items():
                if str(v.get("order_id", "")).strip() == order_id:
                    gefunden_key = k
                    break
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
                "key": gefunden_key,
                "headline": "Lizenz deaktiviert",
                "show_on": ["receipt_page", "order_confirmation_email"]
            }), 200

        return jsonify({
            "status": "success",
            "key": "Keine passende Lizenz gefunden.",
            "headline": "Lizenzstatus",
            "show_on": ["receipt_page", "order_confirmation_email"]
        }), 200

    # Kauf / Aktivierung
    vorhandener_key = None

    if order_id:
        for k, v in keys.items():
            if str(v.get("order_id", "")).strip() == order_id:
                vorhandener_key = k
                break

    if not vorhandener_key and lizenz_key:
        vorhandener_key = lizenz_key

    if not vorhandener_key and buyer_email and product_id:
        for k, v in keys.items():
            if (
                str(v.get("buyer_email", "")).strip().lower() == buyer_email
                and str(v.get("product_id", "")).strip() == product_id
                and v.get("active", False)
            ):
                vorhandener_key = k
                break

    if not vorhandener_key:
        vorhandener_key = "TM-" + str(uuid.uuid4())[:12].upper()

    keys[vorhandener_key] = {
        "active": True,
        "buyer_email": buyer_email,
        "order_id": order_id,
        "product_id": product_id,
        "event": event or "purchase",
        "machine_id": keys.get(vorhandener_key, {}).get("machine_id", "")
    }

    speichere_keys(keys)

    return jsonify({
        "status": "success",
        "key": vorhandener_key,
        "headline": "Dein Lizenzschlüssel",
        "show_on": ["receipt_page", "order_confirmation_email"]
    }), 200


# ===============================
# GRATIS-KEY ERZEUGEN (GESCHÜTZT)
# ===============================
@app.route("/create_free_key", methods=["POST", "GET"])
def create_free_key():
    secret = request.args.get("secret", "").strip()

    if secret != RESET_SECRET:
        return jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 403

    data = lese_request_daten()
    if not data:
        data = request.args.to_dict()

    buyer_email = str(
        data.get("buyer_email")
        or data.get("email")
        or "FREE"
    ).strip().lower()

    keys = lade_keys()

    for key, eintrag in keys.items():
        if (
            str(eintrag.get("buyer_email", "")).strip().lower() == buyer_email
            and str(eintrag.get("event", "")).strip().lower() == "free"
            and eintrag.get("active", False)
        ):
            return jsonify({
                "ok": True,
                "key": key,
                "buyer_email": buyer_email,
                "message": "Vorhandener Free-Key wiederverwendet"
            })

    neuer_key = "TM-" + str(uuid.uuid4())[:12].upper()

    keys[neuer_key] = {
        "active": True,
        "buyer_email": buyer_email,
        "order_id": "FREE",
        "product_id": "FREE",
        "event": "free",
        "machine_id": ""
    }

    speichere_keys(keys)

    return jsonify({
        "ok": True,
        "key": neuer_key,
        "buyer_email": buyer_email,
        "message": "Neuer Free-Key erstellt"
    })


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
        keys[key]["event"] = "deactivated"
        speichere_keys(keys)

    return jsonify({"ok": True})


# ===============================
# ALLE KEYS ZURÜCKSETZEN
# ===============================
@app.route("/reset_all_keys", methods=["POST"])
def reset_all_keys():
    secret = request.args.get("secret", "").strip()

    if secret != RESET_SECRET:
        return jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 403

    speichere_keys({})

    return jsonify({
        "ok": True,
        "message": "Alle Keys wurden gelöscht"
    })


# ===============================
# EINZELNEN KEY LÖSCHEN
# ===============================
@app.route("/delete_key", methods=["POST"])
def delete_key():
    secret = request.args.get("secret", "").strip()

    if secret != RESET_SECRET:
        return jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 403

    data = lese_request_daten()
    key = hole_key_aus_daten(data)

    if not key:
        return jsonify({
            "ok": False,
            "error": "no_key"
        }), 400

    keys = lade_keys()

    if key not in keys:
        return jsonify({
            "ok": False,
            "error": "not_found"
        }), 404

    del keys[key]
    speichere_keys(keys)

    return jsonify({
        "ok": True,
        "deleted_key": key
    })


# ===============================
# EINZELNEN KEY DEAKTIVIEREN (GESCHÜTZT)
# ===============================
@app.route("/disable_key", methods=["POST"])
def disable_key():
    secret = request.args.get("secret", "").strip()

    if secret != RESET_SECRET:
        return jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 403

    data = lese_request_daten()
    key = hole_key_aus_daten(data)

    if not key:
        return jsonify({
            "ok": False,
            "error": "no_key"
        }), 400

    keys = lade_keys()

    if key not in keys:
        return jsonify({
            "ok": False,
            "error": "not_found"
        }), 404

    keys[key]["active"] = False
    keys[key]["event"] = "disabled_by_admin"
    speichere_keys(keys)

    return jsonify({
        "ok": True,
        "disabled_key": key
    })


# ===============================
# EINZELNEN KEY AKTIVIEREN (GESCHÜTZT)
# ===============================
@app.route("/enable_key", methods=["POST"])
def enable_key():
    secret = request.args.get("secret", "").strip()

    if secret != RESET_SECRET:
        return jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 403

    data = lese_request_daten()
    key = hole_key_aus_daten(data)

    if not key:
        return jsonify({
            "ok": False,
            "error": "no_key"
        }), 400

    keys = lade_keys()

    if key not in keys:
        return jsonify({
            "ok": False,
            "error": "not_found"
        }), 404

    keys[key]["active"] = True
    keys[key]["event"] = "enabled_by_admin"
    speichere_keys(keys)

    return jsonify({
        "ok": True,
        "enabled_key": key
    })


# ===============================
# LICENSE PAGE
# ===============================
@app.route("/license")
def license_page():
    email = request.args.get("buyer_email", "").strip().lower()

    keys = lade_keys()

    for key, data in keys.items():
        if data.get("buyer_email", "").strip().lower() == email:
            status = "AKTIV" if data.get("active", False) else "GESPERRT"
            machine_id = data.get("machine_id", "")
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
                    <div class="small">Gerätebindung: {{ machine_id if machine_id else "noch nicht gebunden" }}</div>
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
            """, key=key, status=status, machine_id=machine_id)

    return "<h1>Kein Key gefunden</h1>"


# ===============================
# ADMIN PANEL
# ===============================
@app.route("/admin")
def admin_panel():
    if not admin_auth_ok():
        return (
            "Login erforderlich",
            401,
            {"WWW-Authenticate": 'Basic realm="Admin Login"'}
        )

    keys = lade_keys()

    rows = []
    for key, data in keys.items():
        status = "AKTIV" if data.get("active", False) else "GESPERRT"
        buyer_email = data.get("buyer_email", "")
        order_id = data.get("order_id", "")
        product_id = data.get("product_id", "")
        event = data.get("event", "")
        machine_id = data.get("machine_id", "")

        rows.append(f"""
        <tr>
            <td>{key}</td>
            <td>{status}</td>
            <td>{buyer_email}</td>
            <td>{order_id}</td>
            <td>{product_id}</td>
            <td>{event}</td>
            <td>{machine_id}</td>
            <td>
                <form method="post" action="/admin/enable" style="display:inline;">
                    <input type="hidden" name="key" value="{key}">
                    <button type="submit" style="background:#0a7f2e;color:white;">Aktivieren</button>
                </form>
                <form method="post" action="/admin/disable" style="display:inline; margin-left:8px;">
                    <input type="hidden" name="key" value="{key}">
                    <button type="submit">Deaktivieren</button>
                </form>
                <form method="post" action="/admin/delete" style="display:inline; margin-left:8px;">
                    <input type="hidden" name="key" value="{key}">
                    <button type="submit" style="background:#b00020;color:white;">Löschen</button>
                </form>
            </td>
        </tr>
        """)

    html = f"""
    <!DOCTYPE html>
    <html lang="de">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Admin Panel</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #0b0b0e;
                color: white;
                margin: 0;
                padding: 30px;
            }}
            h1 {{
                margin-top: 0;
            }}
            .topbar {{
                display:flex;
                justify-content:space-between;
                align-items:flex-start;
                margin-bottom:20px;
                gap: 12px;
                flex-wrap: wrap;
            }}
            .right-tools {{
                display:flex;
                flex-direction:column;
                gap:12px;
                align-items:flex-end;
            }}
            .free-form {{
                display:flex;
                gap:8px;
                flex-wrap:wrap;
                align-items:center;
                justify-content:flex-end;
            }}
            .free-form input {{
                padding:10px 12px;
                border-radius:10px;
                border:none;
                min-width:260px;
            }}
            .btn {{
                padding: 10px 16px;
                border: none;
                border-radius: 10px;
                cursor: pointer;
                background: #2b56ff;
                color: white;
                font-size: 14px;
            }}
            .danger {{
                background: #b00020;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                background: #171717;
                border-radius: 12px;
                overflow: hidden;
            }}
            th, td {{
                padding: 12px;
                border-bottom: 1px solid #333;
                text-align: left;
                vertical-align: top;
                font-size: 14px;
            }}
            th {{
                background: #1f1f1f;
            }}
            tr:hover {{
                background: #202020;
            }}
            button {{
                padding: 8px 12px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
            }}
            .empty {{
                margin-top: 20px;
                color: #bbb;
            }}
        </style>
    </head>
    <body>
        <div class="topbar">
            <h1>Lizenz Admin Panel</h1>

            <div class="right-tools">
                <form method="post" action="/admin/create_free_key" class="free-form">
                    <input
                        type="email"
                        name="buyer_email"
                        placeholder="kollege@mail.de"
                        required
                    >
                    <button class="btn" type="submit">Free Key erstellen</button>
                </form>

                <form method="post" action="/admin/reset_all" onsubmit="return confirm('Wirklich alle Keys löschen?');">
                    <button class="btn danger" type="submit">Alle Keys löschen</button>
                </form>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Key</th>
                    <th>Status</th>
                    <th>E-Mail</th>
                    <th>Order ID</th>
                    <th>Product ID</th>
                    <th>Event</th>
                    <th>Machine ID</th>
                    <th>Aktionen</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows) if rows else '<tr><td colspan="8" class="empty">Keine Keys vorhanden.</td></tr>'}
            </tbody>
        </table>
    </body>
    </html>
    """
    return html


@app.route("/admin/create_free_key", methods=["POST"])
def admin_create_free_key():
    if not admin_auth_ok():
        return (
            "Login erforderlich",
            401,
            {"WWW-Authenticate": 'Basic realm="Admin Login"'}
        )

    buyer_email = request.form.get("buyer_email", "").strip().lower()
    keys = lade_keys()

    if not buyer_email:
        return "", 302, {"Location": "/admin"}

    for key, eintrag in keys.items():
        if (
            str(eintrag.get("buyer_email", "")).strip().lower() == buyer_email
            and str(eintrag.get("event", "")).strip().lower() == "free"
            and eintrag.get("active", False)
        ):
            return "", 302, {"Location": "/admin"}

    neuer_key = "TM-" + str(uuid.uuid4())[:12].upper()

    keys[neuer_key] = {
        "active": True,
        "buyer_email": buyer_email,
        "order_id": "FREE",
        "product_id": "FREE",
        "event": "free",
        "machine_id": ""
    }

    speichere_keys(keys)
    return "", 302, {"Location": "/admin"}


@app.route("/admin/enable", methods=["POST"])
def admin_enable():
    if not admin_auth_ok():
        return (
            "Login erforderlich",
            401,
            {"WWW-Authenticate": 'Basic realm="Admin Login"'}
        )

    key = request.form.get("key", "").strip()
    keys = lade_keys()

    if key in keys:
        keys[key]["active"] = True
        keys[key]["event"] = "enabled_by_admin"
        speichere_keys(keys)

    return "", 302, {"Location": "/admin"}


@app.route("/admin/disable", methods=["POST"])
def admin_disable():
    if not admin_auth_ok():
        return (
            "Login erforderlich",
            401,
            {"WWW-Authenticate": 'Basic realm="Admin Login"'}
        )

    key = request.form.get("key", "").strip()
    keys = lade_keys()

    if key in keys:
        keys[key]["active"] = False
        keys[key]["event"] = "disabled_by_admin"
        speichere_keys(keys)

    return "", 302, {"Location": "/admin"}


@app.route("/admin/delete", methods=["POST"])
def admin_delete():
    if not admin_auth_ok():
        return (
            "Login erforderlich",
            401,
            {"WWW-Authenticate": 'Basic realm="Admin Login"'}
        )

    key = request.form.get("key", "").strip()
    keys = lade_keys()

    if key in keys:
        del keys[key]
        speichere_keys(keys)

    return "", 302, {"Location": "/admin"}


@app.route("/admin/reset_all", methods=["POST"])
def admin_reset_all():
    if not admin_auth_ok():
        return (
            "Login erforderlich",
            401,
            {"WWW-Authenticate": 'Basic realm="Admin Login"'}
        )

    speichere_keys({})
    return "", 302, {"Location": "/admin"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
