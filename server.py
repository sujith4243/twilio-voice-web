from flask import Flask,request
from twilio.twiml.voice_response import VoiceResponse, Gather
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

@app.route("/")
def index():
    return "Voice app is running"

@app.route("/incoming", methods=["POST"])
def incoming():
    response = VoiceResponse()
    gather = Gather(num_digits=1, action="/set_language", method="GET")
    gather.say("For English, press 1. Para español, oprima 2.", language="en-US")
    response.append(gather)
    return str(response)

@app.route("/set_language", methods=["GET"])
def set_language():
    digit = request.args.get("Digits", "")
    response = VoiceResponse()
    if digit == "1":
        language = "en-US"
    elif digit == "2":
        language = "es-ES"
    else:
        response.say("Invalid selection. Please try again.")
        response.redirect("/incoming")
        return str(response)

    gather = Gather(num_digits=4, action=f"/validate_pin?language={language}", method="GET")
    gather.say("Please enter your 4 digit PIN.", language=language)
    response.append(gather)
    return str(response)

@app.route("/validate_pin", methods=["GET"])
def validate_pin():
    language = request.args.get("language", "en-US")
    digit = request.args.get("Digits", "")
    response = VoiceResponse()

    if digit == "1234":
        gather = Gather(num_digits=1, action=f"/menu?language={language}", method="GET")
        gather.say("Press 1 to leave a voicemail.", language=language)
        response.append(gather)
    else:
        response.say("Invalid PIN. Try again.", language=language)
        response.redirect("/incoming")
    return str(response)

@app.route("/menu", methods=["GET"])
def menu():
    digit = request.args.get("Digits", "")
    language = request.args.get("language", "en-US")
    response = VoiceResponse()

    if digit == "1":
        response.say("Please leave your message after the beep. Press the pound key when done.", language=language)
        response.record(maxLength=120, action="/voicemail", method="POST", transcribe=True)
    else:
        response.say("Invalid option. Returning to main menu.", language=language)
        response.redirect("/incoming")

    return str(response)

@app.route("/voicemail", methods=["POST"])
def voicemail():
    recording_url = request.form.get("RecordingUrl")
    transcription = request.form.get("TranscriptionText", "[No transcription]")
    print(f"[Voicemail] Recording: {recording_url}")
    print(f"[Transcription] {transcription}")

    response = VoiceResponse()
    response.say("Thank you. Your voicemail has been recorded.", language="en-US")
    return str(response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
