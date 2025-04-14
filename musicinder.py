import os
import requests
from flask import Flask, request, jsonify, session
from pyngrok import ngrok
from langchain_huggingface import HuggingFaceEndpoint

# main configuration
WHATSAPP_API_URL = "WHATSAPP_API_URL"
ACCESS_TOKEN = "WHATSAPP_ACESS_TOKEN"
VERIFY_TOKEN = "YOUR_TOKEN"
HF_ENDPOINT_URL = "YOUR_HF_ENDPOINT"
HF_API_KEY = "YOUR_HF_KEY"
NGROK_AUTH_TOKEN = "YOUR_NGROK_TOKEN"
GENIUS_API_KEY = "YOUR_GENIUS_KEY"

app = Flask(__name__)
app.secret_key = "YOUR_SECRET_KEY"

session_state = {}


# Function to search for music by part of the lyrics
def search_song_by_lyrics(lyrics):
    base_url = "https://api.genius.com/search"
    headers = {"Authorization": f"Bearer {GENIUS_API_KEY}"}
    params = {"q": lyrics}

    response = requests.get(base_url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        hits = data.get("response", {}).get("hits", [])

        if hits:
            first_hit = hits[0]["result"]
            song_title = first_hit["title"]
            artist_name = first_hit["primary_artist"]["name"]
            return f"Music found: {song_title} - {artist_name}"
        else:
            return "No songs found with this excerpt."
    else:
        return "Error requesting the Genius API."

# Function for whatsapp messages
def send_whatsapp_messages(to_number, messages):
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    for message_body in messages:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": message_body},
        }
        response = requests.post(WHATSAPP_API_URL, json=payload, headers=headers)
        if response.status_code == 200:
            print(f"Mensagem enviada!")
        else:
            print(f"Erro ao enviar mensagem: {response.text}")

llm = HuggingFaceEndpoint(
    endpoint_url=HF_ENDPOINT_URL,
    huggingfacehub_api_token=HF_API_KEY,
    task="text-generation"
)


def generate_response(message, from_number):
    try:
        prompt = f"Answer with a maximum of 3 sentences: {message}"
        response = llm(prompt)
        return response.strip() if response else "I was unable to process your request."
    except Exception as e:
        print(f"[ERRO] Failed to generate response: {str(e)}")
        return "An error occurred while processing your message. Please try again later."

def process_message(from_number, message):
    global session_state
    usuario = session_state.get(from_number, "inicio")

    if usuario == "inicio":
        response_messages = [
            "Olá!",
            "Sou um serviço de procura musical.",
            "Tente mandar a letra da música ou um áudio com trecho dela!"
        ]
        send_whatsapp_messages(from_number, response_messages)
        session_state[from_number] = "esperando_mensagem"

    elif usuario == "esperando_mensagem":
        message_type = message.get("type", "text")

        if message_type == "text":
            message_body = message.get("text", {}).get("body", "").strip().lower()

            if message_body:
                resposta = search_song_by_lyrics(message_body)
                send_whatsapp_messages(from_number, [resposta, 'Se não está correta, digite "incorreta" para falar com a IA.'])
                session_state[from_number] = "inicio"

            if message_body == "incorreta":
                send_whatsapp_messages(from_number, ["Aguarde, estou processando sua mensagem."])
                model_response = generate_response(message_body)
                send_whatsapp_messages(from_number, [model_response])
                session_state[from_number] = "inicio"

        elif message_type == "audio":
            send_whatsapp_messages(from_number, ["Recebi um áudio! Ainda estou aprendendo a reconhecer músicas pelo som."])
            session_state[from_number] = "inicio"

    return jsonify({"status": "Mensagem processada!"}), 200

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if verify_token == VERIFY_TOKEN:
            return challenge, 200
        return "Token de verificação inválido", 403
    elif request.method == 'POST':
        data = request.get_json()
        print(f"Dados recebidos: {data}")
        if not data:
            return "Dados inválidos", 400
        try:
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    messages = value.get('messages', [])
                    for message in messages:
                        from_number = message.get('from')
                        process_message(from_number, message)
        except Exception as e:
            app.logger.error(f"Erro ao processar a mensagem: {e}")
            return "Erro interno", 500
        return jsonify({"status": "Mensagem processada"}), 200

if __name__ == "__main__":
    ngrok.set_auth_token(NGROK_AUTH_TOKEN)
    public_url = ngrok.connect(5000)
    print(f"Public Webhook in: {public_url.public_url}/webhook")
    app.run(host="0.0.0.0", port=5000)
