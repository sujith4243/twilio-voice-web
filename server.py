import os
import sqlite3
from datetime import datetime

from flask import Flask, request, jsonify, render_template, Response, g, redirect, url_for
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial
from dotenv import load_dotenv
import openai
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client as TwilioRestClient

# -----------------------------------------------------------------------------
# 🛠  ENVIRONMENT & CONFIG ------------------------------------------------------
# -----------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# Twilio credentials
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
API_KEY_SID = os.getenv("TWILIO_API_KEY_SID")
API_KEY_SECRET = os.getenv("TWILIO_API_KEY_SECRET")
TWIML_APP_SID = os.getenv("TWIML_APP_SID")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:5000")

# OpenAI & SendGrid
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO")  # where to send voicemail alerts

openai.api_key = OPENAI_API_KEY

twilio_client = TwilioRestClient(ACCOUNT_SID, os.getenv("TWILIO_AUTH_TOKEN"))

# -----------------------------------------------------------------------------
# 💾 DATABASE (SQLite) ---------------------------------------------------------
# -----------------------------------------------------------------------------
DATABASE = "call_logs.db"

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.execute(
            """CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_number TEXT,
                to_number TEXT,
                start_time TEXT,
                end_time TEXT,
                duration REAL,
                recording_url TEXT,
                transcription TEXT
            )"""
        )
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

# -----------------------------------------------------------------------------
# 🔐 SIMPLE PIN VALIDATION ------------------------------------------------------
# -----------------------------------------------------------------------------
PIN_CODE = os.getenv("APP_PIN", "1234")

# -----------------------------------------------------------------------------
# 🌐 ROUTES --------------------------------------------------------------------
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/favicon.ico")
def favicon():
    return "", 204

# -----------------------------------------------------------------------------
# 🎫 TOKEN ENDPOINT ------------------------------------------------------------
# -----------------------------------------------------------------------------
@app.route("/token", methods=["GET"])
def token():
    identity = request.args.get("identity", "user123")
    token = AccessToken(ACCOUNT_SID, API_KEY_SID, API_KEY_SECRET, identity=identity)
    voice_grant = VoiceGrant(outgoing_application_sid=TWIML_APP_SID, incoming_allow=True)
    token.add_grant(voice_grant)
    jwt = token.to_jwt()
    return jsonify(token=jwt.decode() if hasattr(jwt, "decode") else jwt)

# -----------------------------------------------------------------------------
# ☎️ INCOMING CALL HANDLER ------------------------------------------------------
# -----------------------------------------------------------------------------
@app.route("/incoming", methods=["POST"])
def incoming():
    response = VoiceResponse()

    # 1️⃣  Ask for preferred language (1-English, 2-Spanish, 3-Hindi as example)
    gather_lang = Gather(num_digits=1, action=url_for("set_language", _external=True), method="POST")
    gather_lang.say("For English press 1. Para Español presione 2. हिन्दी के लिये 3 दबाएँ.")
    response.append(gather_lang)
    response.redirect(url_for("incoming", _external=True))
    return Response(str(response), mimetype="text/xml")

# -----------------------------------------------------------------------------
# 🌐 LANGUAGE SELECTION ---------------------------------------------------------
# -----------------------------------------------------------------------------
@app.route("/set_language", methods=["GET", "POST"])
def set_language():
    lang_digit = request.values.get("Digits", "1")  
    lang_map = {"1": "en-US", "2": "es-ES", "3": "hi-IN"}
    language = lang_map.get(lang_digit, "en-US")

    response = VoiceResponse()

    # 2️⃣  PIN validation
    gather_pin = Gather(num_digits=len(PIN_CODE), action=url_for("validate_pin", language=language, _external=True), method="POST")
    gather_pin.say("Please enter your PIN to continue.", language=language)
    response.append(gather_pin)
    response.say("No input received. Goodbye.", language=language)
    return Response(str(response), mimetype="text/xml")

# -----------------------------------------------------------------------------
# 🔒 PIN VALIDATION ------------------------------------------------------------
# -----------------------------------------------------------------------------
@app.route("/validate_pin", methods=["GET", "POST"])
def validate_pin():
    language = request.args.get("language", "en-US")
    digits   = request.values.get("Digits", "")   # ← unified source
    response = VoiceResponse()

    if digits == PIN_CODE:
        # good PIN → go to menu
        gather_menu = Gather(
            num_digits=1,
            action=url_for("menu", language=language, _external=True),
            method="POST"
        )
        gather_menu.say(
            "Press 1 to talk to the AI assistant. "
            "Press 2 to leave a voicemail.",
            language=language
        )
        response.append(gather_menu)
        response.say("No input received. Goodbye.", language=language)
    else:
        response.say("Incorrect PIN. Goodbye.", language=language)

    return Response(str(response), mimetype="text/xml")

# -----------------------------------------------------------------------------
# 📜 MAIN MENU -----------------------------------------------------------------
# -----------------------------------------------------------------------------
@app.route("/menu", methods=["GET", "POST"])
def menu():
    language = request.args.get("language", "en-US")
    digit = request.form.get("Digits", "")
    response = VoiceResponse()

    if digit == "1":
        # AI assistant flow
        response.say("Connecting you to the assistant. Please say your question after the beep.", language=language)
        response.record(max_length=30, action=url_for("ai_assistant", language=language, _external=True), play_beep=True)
    elif digit == "2":
        # Voicemail flow directly
        response.say("Please leave your message after the beep.", language=language)
        response.record(max_length=120, action=url_for("handle_voicemail", language=language, _external=True), transcribe=True, transcribe_callback=url_for("save_transcription", _external=True), play_beep=True)
    else:
        response.say("Invalid option.", language=language)
        response.redirect(url_for("incoming", _external=True))

    return Response(str(response), mimetype="text/xml")

# -----------------------------------------------------------------------------
# 🤖 AI ASSISTANT --------------------------------------------------------------
# -----------------------------------------------------------------------------
@app.route("/ai_assistant", methods=["POST"])
def ai_assistant():
    language = request.args.get("language", "en-US")
    recording_url = request.form.get("RecordingUrl")

    # Simple transcription using Twilio (could use Whisper)
    transcript = request.form.get("TranscriptionText", "")

    # Fallback: if no transcription, fetch recording and send to Whisper (skipped for brevity)

    prompt = f"Caller asked: {transcript}. Provide a concise helpful answer."

    ai_response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "You are a helpful phone assistant."},
                  {"role": "user", "content": prompt}],
        max_tokens=100
    )
    answer_text = ai_response.choices[0].message["content"].strip()

    response = VoiceResponse()
    response.say(answer_text, language=language)
    response.hangup()

    # Log the call
    save_call_log(from_num=request.form.get("From"), to_num=request.form.get("To"), recording_url=recording_url, transcription=transcript)
    return Response(str(response), mimetype="text/xml")

# -----------------------------------------------------------------------------
# 📞 VOICEMAIL HANDLER ---------------------------------------------------------
# -----------------------------------------------------------------------------
@app.route("/handle_voicemail", methods=["POST"])
def handle_voicemail():
    language = request.args.get("language", "en-US")
    recording_url = request.form.get("RecordingUrl")
    from_num = request.form.get("From")

    # Send alerts
    send_sms_alert(from_num, recording_url)
    send_email_alert(from_num, recording_url)

    response = VoiceResponse()
    response.say("Thank you. Your message has been recorded. Goodbye.", language=language)
    response.hangup()

    # Log the call
    save_call_log(from_num=from_num, to_num=request.form.get("To"), recording_url=recording_url)
    return Response(str(response), mimetype="text/xml")

# -----------------------------------------------------------------------------
# 📝 SAVE TRANSCRIPTION CALLBACK ----------------------------------------------
# -----------------------------------------------------------------------------
@app.route("/save_transcription", methods=["POST"])
def save_transcription():
    recording_sid = request.form.get("RecordingSid")
    transcription_text = request.form.get("TranscriptionText")
    db = get_db()
    db.execute("UPDATE calls SET transcription=? WHERE recording_url LIKE ?", (transcription_text, f"%{recording_sid}%"))
    db.commit()
    return "", 204

# -----------------------------------------------------------------------------
# 📤 OUTGOING DIAL -------------------------------------------------------------
# -----------------------------------------------------------------------------
@app.route("/outgoing", methods=["POST"])
def outgoing():
    number = request.form.get("To")
    response = VoiceResponse()
    if number:
        dial = Dial(callerId=TWILIO_NUMBER)
        dial.number(number)
        response.append(dial)
    else:
        response.say("Missing 'To' parameter.")
    return Response(str(response), mimetype="text/xml")

# -----------------------------------------------------------------------------
# 📊 UTILITY: SAVE CALL LOG ----------------------------------------------------
# -----------------------------------------------------------------------------

def save_call_log(from_num=None, to_num=None, recording_url=None, transcription=None):
    db = get_db()
    start_time = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO calls (from_number, to_number, start_time, recording_url, transcription) VALUES (?, ?, ?, ?, ?)",
        (from_num, to_num, start_time, recording_url, transcription),
    )
    db.commit()

# -----------------------------------------------------------------------------
# 📩 ALERT HELPERS -------------------------------------------------------------
# -----------------------------------------------------------------------------

def send_sms_alert(from_num, recording_url):
    if not from_num or not recording_url:
        return
    body = f"Missed call from {from_num}. Voicemail: {recording_url}"
    twilio_client.messages.create(body=body, from_=TWILIO_NUMBER, to=os.getenv("ALERT_SMS_TO", from_num))

def send_email_alert(from_num, recording_url):
    if not SENDGRID_API_KEY or not ALERT_EMAIL_TO:
        return
    message = Mail(
        from_email="noreply@yourapp.com",
        to_emails=ALERT_EMAIL_TO,
        subject="New Voicemail Received",
        html_content=f"<p>Missed call from {from_num}.<br>Voicemail: <a href='{recording_url}'>Listen</a></p>"
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        sg.send(message)
    except Exception as e:
        app.logger.error(f"SendGrid error: {e}")

# -----------------------------------------------------------------------------
# 🚀 MAIN ---------------------------------------------------------------------
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
