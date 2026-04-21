from flask import Flask, request, jsonify

app = Flask(__name__)

VALID_KEYS = {
    "ABC123-XYZ": {"active": True},
    "TEST-KEY-123": {"active": True}
}

BLOCKED_KEYS = []

@app.route("/check_key")
def check_key():
    key = request.args.get("key")

    if key in BLOCKED_KEYS:
        return jsonify({"valid": False})

    if key in VALID_KEYS and VALID_KEYS[key]["active"]:
        return jsonify({"valid": True})

    return jsonify({"valid": False})

@app.route("/")
def home():
    return "License Server läuft!"

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
