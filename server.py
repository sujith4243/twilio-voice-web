"""
server.py – Twilio Voice demo with IVR menu + voicemail SMS notification
-------------------------------------------------------------------------
• Generates client tokens (/token)
• Handles an IVR menu for incoming calls (/incoming, /menu)
• Places outbound calls and records voicemail if the callee
  doesn’t pick up within 20 s (/outgoing → /voicemail → /handle_recording)
• Sends SMS when voicemail is received
"""

from flask import Flask, request, jsonify, render_template, Response
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial, Record, Say
from twilio.rest import Client
from dotenv import load_dotenv
from datetime import datetime
import os

# --------------------------------------------------------------------
# Environment / Flask setup
# --------------------------------------------------------------------
load_dotenv()
app = Flask(__name__, template_folder="templates")

# Twilio credentials (stored in .env or Render environment variables)
account_sid        = os.getenv("TWILIO_ACCOUNT_SID")
api_key_sid        = os.getenv("TWILIO_API_KEY_SID")
api_key_secret     = os.getenv("TWILIO_API_KEY_SECRET")
twiml_app_sid      = os.getenv("TWIML_APP_SID")
twilio_number      = os.getenv("TWILIO_NUMBER")
twilio_auth_token  = os.getenv("TWILIO_AUTH_TOKEN")  # REQUIRED for SMS

# Public URL for webhook responses
public_url         = os.getenv("PUBLIC_URL", "http://localhost:5000")

# Twilio REST client (for sending SMS notifications)
twilio_client = Client(account_sid, twilio_auth_token)

# --------------------------------------------------------------------
# Front page
# --------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/favicon.ico")
def favicon():
    return "", 204

# --------------------------------------------------------------------
# 1️⃣ Client access token
# --------------------------------------------------------------------
@app.route("/token", methods=["GET"])
def token():
    identity = request.args.get("identity", "user123")
    tok      = AccessToken(account_sid, api_key_sid, api_key_secret, identity=identity)
    tok.add_grant(VoiceGrant(outgoing_application_sid=twiml_app_sid, incoming_allow=True))
    jwt_str = tok.to_jwt()
    if hasattr(jwt_str, "decode"):
        jwt_str = jwt_str.decode()
    return jsonify(token=jwt_str)

# --------------------------------------------------------------------
# 2️⃣ IVR: incoming call → menu → queue
# --------------------------------------------------------------------
@app.route("/incoming", methods=["POST"])
def incoming():
    print("📞 Incoming call")
    resp   = VoiceResponse()
    gather = Gather(num_digits=1, action=f"{public_url}/menu", method="POST")
    gather.say("Welcome to the demo. Press 1 for Sales. Press 2 for Support.",
               voice="alice", language="en-AU")
    resp.append(gather)
    resp.say("We didn't receive any input. Goodbye.")
    return Response(str(resp), mimetype="text/xml")

@app.route("/menu", methods=["POST"])
def menu():
    digit = request.form.get("Digits")
    print(f"📲 Menu choice: {digit}")
    resp = VoiceResponse()

    if digit == "1":
        resp.say("Transferring to Sales.", voice="alice")
        dial = resp.dial(record="record-from-answer")
        dial.queue("sales-support",
                   url="http://com.twilio.music.classical.s3.amazonaws.com/BusyStrings.mp3")
    elif digit == "2":
        resp.say("Transferring to Support.", voice="alice")
        dial = resp.dial(record="record-from-answer")
        dial.queue("sales-support",
                   url="http://com.twilio.music.classical.s3.amazonaws.com/BusyStrings.mp3")
    else:
        resp.say("Invalid option.", voice="alice")
        resp.redirect("/incoming")
    return Response(str(resp), mimetype="text/xml")

# --------------------------------------------------------------------
# 3️⃣ Outgoing call → voicemail fallback
# --------------------------------------------------------------------
@app.route("/outgoing", methods=["POST"])
def outgoing():
    number = request.form.get("To")
    resp   = VoiceResponse()

    if number:
        dial = resp.dial(callerId=twilio_number,
                         timeout=20,
                         action=f"{public_url}/voicemail",
                         method="POST")
        dial.number(number)
    else:
        resp.say("Missing 'To' number. Cannot place call.", voice="alice")
    return Response(str(resp), mimetype="text/xml")

@app.route("/voicemail", methods=["POST"])
def voicemail():
    resp = VoiceResponse()
    resp.say("Sorry, no one could take your call. "
             "Please leave a message after the beep. "
             "Press the pound key when you're finished.",
             voice="alice", language="en-AU")
    resp.record(max_length=120,
                play_beep=True,
                finish_on_key="#",
                action=f"{public_url}/handle_recording",
                method="POST")
    resp.say("We didn't get your message. Goodbye.", voice="alice")
    resp.hangup()
    return Response(str(resp), mimetype="text/xml")

@app.route("/handle_recording", methods=["POST"])
def handle_recording():
    recording_url = request.form.get("RecordingUrl")
    caller        = request.form.get("From")
    timestamp     = datetime.now().isoformat(timespec="seconds")

    print(f"[Voicemail] {caller} at {timestamp} -> {recording_url}")

    # 🔔 Send SMS Notification
    try:
        twilio_client.messages.create(
            body=f"📨 New voicemail from {caller} at {timestamp}:\n{recording_url}",
            from_=twilio_number,
            to="+61XXXXXXXXX"  # 🔁 Replace with your personal mobile number
        )
        print("✅ SMS notification sent.")
    except Exception as e:
        print(f"❌ Error sending SMS: {e}")

    resp = VoiceResponse()
    resp.say("Thanks, your message has been recorded. Goodbye.",
             voice="alice", language="en-AU")
    resp.hangup()
    return Response(str(resp), mimetype="text/xml")

# --------------------------------------------------------------------
# Gunicorn entry point
# --------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🟢 Flask dev server on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
