import os
import sys
import threading
import time
import urllib.request
import json
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_agent.chatbot import DNHChatbot

load_dotenv()

def test_bot():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    print("Token found:", token)
    if not token:
        print("No token!")
        return
        
    print("Instantiating chatbot...")
    try:
        chatbot = DNHChatbot()
        print("Chatbot instantiated successfully!")
    except Exception as e:
        print("Failed to instantiate chatbot:", e)
        import traceback
        traceback.print_exc()
        return
        
    print("Entering polling loop...")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}"
            print("Polling URL:", url)
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as response:
                res = json.loads(response.read().decode('utf-8'))
                print("Polled response OK:", res.get("ok"))
                for update in res.get("result", []):
                    update_id = update["update_id"]
                    offset = update_id + 1
                    
                    message = update.get("message")
                    if not message:
                        continue
                    chat_id = message["chat"]["id"]
                    text = message.get("text", "")
                    print(f"Received message: '{text}' from chat {chat_id}")
                    
                    reply = chatbot.ask(text)
                    print("Generated reply:", reply.get("answer"))
        except Exception as e:
            print("Error in loop:", e)
            time.sleep(5)

if __name__ == "__main__":
    test_bot()
