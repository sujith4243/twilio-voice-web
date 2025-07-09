from flask import Flask, request, jsonify, render_template, Response
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse, Gather
from dotenv import load_dotenv
import os

load_dotenv()
app = Flask(__name__)

# Load credentials
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
api_key_sid = os.getenv('TWILIO_API_KEY_SID')
api_key_secret = os.getenv('TWILIO_API_KEY_SECRET')
twiml_app_sid = os.getenv('TWIML_APP_SID')
twilio_number = os.getenv('TWILIO_NUMBER')
public_url = os.getenv('PUBLIC_URL', 'http://localhost:5000')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/token', methods=['GET'])
def token():
    identity = request.args.get('identity', 'user123')
    token = AccessToken(account_sid, api_key_sid, api_key_secret, identity=identity)
    voice_grant = VoiceGrant(outgoing_application_sid=twiml_app_sid, incoming_allow=True)
    token.add_grant(voice_grant)
    return jsonify(token=token.to_jwt().decode() if hasattr(token.to_jwt(), 'decode') else token.to_jwt())

@app.route('/incoming', methods=['POST'])
def incoming():
    print("📞 Incoming call received")
    response = VoiceResponse()
    gather = Gather(num_digits=1, action=f"{public_url}/menu", method="POST")
    gather.say("Welcome to the demo. Press 1 for Sales. Press 2 for Support.")
    response.append(gather)
    response.say("We didn't receive any input. Goodbye.")
    return Response(str(response), mimetype='text/xml')

@app.route('/menu', methods=['POST'])
def menu():
    selected_option = request.form.get('Digits')
    print(f"📲 Menu option selected: {selected_option}")
    response = VoiceResponse()

    if selected_option == '1':
        response.say("Transferring to Sales.")
        dial = response.dial(record='record-from-answer')
        dial.queue('sales-support', url='http://com.twilio.music.classical.s3.amazonaws.com/BusyStrings.mp3')
    elif selected_option == '2':
        response.say("Transferring to Support.")
        dial = response.dial(record='record-from-answer')
        dial.queue('sales-support', url='http://com.twilio.music.classical.s3.amazonaws.com/BusyStrings.mp3')
    else:
        response.say("Invalid option.")
        response.redirect('/incoming')

    return Response(str(response), mimetype='text/xml')

@app.route('/outgoing', methods=['POST'])
def outgoing():
    number = request.form.get('To')
    response = VoiceResponse()
    if number:
        dial = response.dial(callerId=twilio_number)
        dial.number(number)
    else:
        response.say("Missing 'To' number. Cannot place call.")
    return Response(str(response), mimetype='text/xml')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🟢 Flask running on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
