"""
server.py – Twilio Voice app with IVR + Voicemail + SMS Notification
"""

from flask import Flask, request, jsonify, render_template, Response
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial
from twilio.rest import Client
from dotenv import load_dotenv
from datetime import datetime
import os

# --------------------------------------------------------------------
# Load environment variables
# --------------------------------------------------------------------
load_dotenv()
app = Flask(__name__, template_folder="templates")

# Twilio credentials from environment
account_sid        = os.getenv("TWILIO_ACCOUNT_SID")
api_key_sid        = os.getenv("TWILIO_API_KEY_SID")
api_key_secret     = os.getenv("TWILIO_API_KEY_SECRET")
twiml_app_sid      = os.getenv("TWIML_APP_SID")
twilio_number      = os.getenv("TWILIO_NUMBER")
twilio_auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
public_url         = os.getenv("PUBLIC_URL")

# Validate critical variables
if not all([account_sid, api_key_sid, api_key_secret, twiml_app_sid, twilio_number, twilio_auth_token, public_url]):
    raise EnvironmentError("Missing one or more required environment variables.")

# Create Twilio REST client
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
# 1️⃣ Generate token for client
# --------------------------------------------------------------------
@app.route("/token", methods=["GET"])
def token():
    identity = request.args.get("identity", "user123")
    access_token = AccessToken(account_sid, api_key_sid, api_key_secret, identity=identity)
    access_token.add_grant(VoiceGrant(outgoing_application_sid=twiml_app_sid, incoming_allow=True))
    jwt_token = access_token.to_jwt()
    return jsonify(token=jwt_token.decode() if hasattr(jwt_token, "decode") else jwt_token)

# --------------------------------------------------------------------
# 2️⃣ Handle incoming call with IVR menu
# --------------------------------------------------------------------
@app.route("/incoming", methods=["POST"])
def incoming():
    print("📞 Incoming call")
    response = VoiceResponse()
    gather = Gather(num_digits=1, action=f"{public_url}/menu", method="POST")
    gather.say("Welcome to the demo. Press 1 for Sales. Press 2 for Support.", voice="alice", language="en-AU")
    response.append(gather)
    response.say("No input received. Goodbye.", voice="alice")
    return Response(str(response), mimetype="text/xml")

@app.route("/menu", methods=["POST"])
def menu():
    digit = request.form.get("Digits")
    print(f"📲 IVR choice: {digit}")
    response = VoiceResponse()

    if digit in ["1", "2"]:
        response.say("Transferring your call.", voice="alice")
        dial = response.dial(record="record-from-answer")
        dial.queue("sales-support", url="http://com.twilio.music.classical.s3.amazonaws.com/BusyStrings.mp3")
    else:
        response.say("Invalid selection.", voice="alice")
        response.redirect("/incoming")

    return Response(str(response), mimetype="text/xml")

# --------------------------------------------------------------------
# 3️⃣ Handle outgoing calls with voicemail fallback
# --------------------------------------------------------------------
@app.route("/outgoing", methods=["POST"])
def outgoing():
    number = request.form.get("To")
    print(f"🚀 Outgoing call to: {number}")
    response = VoiceResponse()

    if number:
        dial = response.dial(
            callerId=twilio_number,
            timeout=20,
            action=f"{public_url}/voicemail",
            method="POST"
        )
        dial.number(number)
    else:
        response.say("Missing phone number.", voice="alice")

    return Response(str(response), mimetype="text/xml")

@app.route("/voicemail", methods=["POST"])
def voicemail():
    print("📩 Voicemail triggered")
    response = VoiceResponse()
    response.say("Sorry, no one could take your call. Please leave a message after the beep. Press the pound key when done.",
                 voice="alice", language="en-AU")
    response.record(
        max_length=120,
        play_beep=True,
        finish_on_key="#",
        action=f"{public_url}/handle_recording",
        method="POST"
    )
    response.say("We didn't receive your message. Goodbye.", voice="alice")
    response.hangup()
    return Response(str(response), mimetype="text/xml")

@app.route("/handle_recording", methods=["POST"])
def handle_recording():
    print("💾 Voicemail recording received")

    recording_url = request.form.get("RecordingUrl")
    caller = request.form.get("From")
    timestamp = datetime.now().isoformat(timespec="seconds")

    if not recording_url:
        print("❗ Missing recording URL")
        return Response("Missing recording URL", status=400)

    print(f"[Voicemail] {caller} at {timestamp} -> {recording_url}")

    try:
        print("📤 Sending SMS alert")
        twilio_client.messages.create(
            body=f"📨 New voicemail from {caller} at {timestamp}:\n{recording_url}",
            from_=twilio_number,
            to="+61475859143"  # <-- Replace with your phone
        )
        print("✅ SMS notification sent.")
    except Exception as e:
        print(f"❌ Error sending SMS: {e}")

    response = VoiceResponse()
    response.say("Thanks, your message has been recorded. Goodbye.", voice="alice", language="en-AU")
    response.hangup()
    return Response(str(response), mimetype="text/xml")

# --------------------------------------------------------------------
# Run server locally (Render uses gunicorn)
# --------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🟢 Flask server running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
