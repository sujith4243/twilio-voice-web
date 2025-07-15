from flask import Flask, request, render_template, Response, url_for
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial
from dotenv import load_dotenv
import os
import sqlite3
from datetime import datetime

app = Flask(__name__)
load_dotenv()

# ----------------- Simple SQLite for voicemail logs -----------------
DB = "voicemails.db"

def log_voicemail(from_num, recording_url, transcription=""):
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS voicemails (id INTEGER PRIMARY KEY AUTOINCREMENT, from_num TEXT, recording_url TEXT, transcription TEXT, ts TEXT)")
    conn.execute("INSERT INTO voicemails (from_num, recording_url, transcription, ts) VALUES (?,?,?,?)", (from_num, recording_url, transcription, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

# ----------------- Incoming call -----------------
@app.route("/incoming", methods=["GET", "POST"])
def incoming_call():
    vr = VoiceResponse()
    gather = Gather(num_digits=1, action=url_for("set_language"), method="POST")
    gather.say("For English press 1. Para español marque dos.")
    vr.append(gather)
    vr.say("We did not receive input. Goodbye.")
    return Response(str(vr), mimetype="text/xml")

# ----------------- Language selection -----------------
@app.route("/set_language", methods=["GET", "POST"])
def set_language():
    digit = request.values.get("Digits", "1")
    language = "en-US" if digit == "1" else "es-ES" if digit == "2" else "en-US"

    vr = VoiceResponse()
    gather = Gather(num_digits=4, action=url_for("validate_pin", language=language), method="POST")
    gather.say("Please enter your four digit PIN.", language=language)
    vr.append(gather)
    vr.say("No input received. Goodbye.", language=language)
    return Response(str(vr), mimetype="text/xml")

# ----------------- PIN validation -----------------
PIN_CODE = "1234"

@app.route("/validate_pin", methods=["GET", "POST"])
def validate_pin():
    language = request.args.get("language", "en-US")
    pin      = request.values.get("Digits", "")
    vr       = VoiceResponse()

    if pin == PIN_CODE:
        gather = Gather(num_digits=1, action=url_for("menu", language=language), method="POST")
        gather.say("Press 1 to leave a voicemail.", language=language)
        vr.append(gather)
        vr.say("No input received. Goodbye.", language=language)
    else:
        vr.say("Invalid PIN. Goodbye.", language=language)
    return Response(str(vr), mimetype="text/xml")

# ----------------- Menu (voicemail only) -----------------
@app.route("/menu", methods=["GET", "POST"])
def menu():
    language = request.args.get("language", "en-US")
    digit    = request.values.get("Digits", "")
    vr       = VoiceResponse()

    if digit == "1":
        vr.say("Please leave your message after the beep.", language=language)
        vr.record(max_length=120,
                  play_beep=True,
                  action=url_for("handle_voicemail", language=language),
                  transcribe=True,
                  transcribe_callback=url_for("save_transcription"))
    else:
        vr.say("Invalid option. Goodbye.", language=language)
    return Response(str(vr), mimetype="text/xml")

# ----------------- Handle voicemail -----------------
@app.route("/handle_voicemail", methods=["POST"])
def handle_voicemail():
    language      = request.args.get("language", "en-US")
    recording_url = request.values.get("RecordingUrl")
    from_num      = request.values.get("From")

    log_voicemail(from_num, recording_url)

    vr = VoiceResponse()
    vr.say("Thank you. Your message has been recorded. Goodbye.", language=language)
    vr.hangup()
    return Response(str(vr), mimetype="text/xml")

# ----------------- Save transcription -----------------
@app.route("/save_transcription", methods=["POST"])
def save_transcription():
    recording_sid = request.values.get("RecordingSid")
    transcription = request.values.get("TranscriptionText", "")
    recording_url = f"https://api.twilio.com/2010-04-01/Accounts/{os.getenv('TWILIO_ACCOUNT_SID')}/Recordings/{recording_sid}"
    log_voicemail(request.values.get("From"), recording_url, transcription)
    return "", 204

# ----------------- Run -----------------
if __name__ == "__main__":
    app.run(port=5000, debug=True)
