# server.py
import os
from flask import Flask, request, Response, jsonify, url_for
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# ------------------ Config ------------------
PIN_CODE        = "1234"                             # change if you wish
TWILIO_NUMBER   = os.getenv("TWILIO_NUMBER")         # your Twilio phone #
ACCOUNT_SID     = os.getenv("TWILIO_ACCOUNT_SID")
API_KEY_SID     = os.getenv("TWILIO_API_KEY_SID")
API_KEY_SECRET  = os.getenv("TWILIO_API_KEY_SECRET")
TWIML_APP_SID   = os.getenv("TWIML_APP_SID")         # created in Twilio Console

# ---------- Incoming: entry -----------------
@app.route("/incoming", methods=["POST"])
def incoming():
    vr = VoiceResponse()
    g  = Gather(num_digits=1, action=url_for("set_language"), method="POST")
    g.say("For English press 1. Para español oprima dos.", language="en-US")
    vr.append(g)
    vr.say("No input received. Goodbye.")
    return Response(str(vr), mimetype="text/xml")

# ---------- Language selection --------------
@app.route("/set_language", methods=["GET", "POST"])
def set_language():
    digit    = request.values.get("Digits", "")
    language = "en-US" if digit == "1" else "es-ES" if digit == "2" else "en-US"

    vr = VoiceResponse()
    g  = Gather(num_digits=len(PIN_CODE),
                action=url_for("validate_pin", language=language),
                method="POST")
    g.say("Please enter your four digit PIN.", language=language)
    vr.append(g)
    vr.say("No input received. Goodbye.", language=language)
    return Response(str(vr), mimetype="text/xml")

# ---------- PIN validation ------------------
@app.route("/validate_pin", methods=["GET", "POST"])
def validate_pin():
    language = request.args.get("language", "en-US")
    digits   = request.values.get("Digits", "")
    vr       = VoiceResponse()

    if digits == PIN_CODE:
        vr.say("Access granted. Thank you.", language=language)
    else:
        vr.say("Invalid PIN. Goodbye.", language=language)
    vr.hangup()
    return Response(str(vr), mimetype="text/xml")

# ---------- Outgoing call -------------------
@app.route("/outgoing", methods=["POST"])
def outgoing():
    """
    POST form-data: To=+61475859143
    Twilio will request this route when you start an outbound call from the JS Client or curl.
    """
    to_number = request.form.get("To")
    vr        = VoiceResponse()
    if to_number:
        dial = Dial(callerId=TWILIO_NUMBER)
        dial.number(to_number)
        vr.append(dial)
    else:
        vr.say("Missing 'To' number.")
    return Response(str(vr), mimetype="text/xml")

# ---------- (Optional) token for JS client ---
@app.route("/token")
def token():
    identity = request.args.get("identity", "webUser")
    tok      = AccessToken(ACCOUNT_SID, API_KEY_SID, API_KEY_SECRET, identity=identity)
    tok.add_grant(VoiceGrant(outgoing_application_sid=TWIML_APP_SID, incoming_allow=True))
    jwt = tok.to_jwt()
    return jsonify(token=jwt.decode() if hasattr(jwt, "decode") else jwt)

# ---------- Run locally ----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
