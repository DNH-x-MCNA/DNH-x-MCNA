import os
import json
import asyncio
from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
    ActivityHandler
)
from botbuilder.schema import Activity
from dotenv import load_dotenv
from ai_agent.chatbot import DNHChatbot

# Ensure env variables are loaded
load_dotenv()

# 1. Initialize Bot Framework Adapter Settings
MICROSOFT_APP_ID = os.getenv("MICROSOFT_APP_ID", "")
MICROSOFT_APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD", "")

# In development, if credentials are empty, the adapter runs in offline emulator mode
SETTINGS = BotFrameworkAdapterSettings(
    app_id=MICROSOFT_APP_ID.strip() if MICROSOFT_APP_ID else "",
    app_password=MICROSOFT_APP_PASSWORD.strip() if MICROSOFT_APP_PASSWORD else ""
)
ADAPTER = BotFrameworkAdapter(SETTINGS)

# 2. Define the Teams Activity Handler
class DNHBot(ActivityHandler):
    def __init__(self, chatbot: DNHChatbot):
        self.chatbot = chatbot

    async def on_message_activity(self, turn_context: TurnContext):
        # Extract user message
        user_message = turn_context.activity.text
        if not user_message:
            return
            
        # Clean Teams mention tag if any (e.g. "<at>DNH Bot</at> Hello" -> "Hello")
        cleaned_message = self._clean_mention(user_message)
        
        # Send a typing indicator while processing
        await turn_context.send_activity(Activity(type="typing"))
        
        try:
            # Query the AI Chatbot
            # Run in executor to avoid blocking the event loop on sync API calls
            loop = asyncio.get_event_loop()
            chatbot_response = await loop.run_in_executor(
                None, self.chatbot.ask, cleaned_message
            )
            
            # Format Markdown Response
            reply_text = f"{chatbot_response['answer']}"
            
            # Append SQL details if present
            if chatbot_response.get("sql"):
                reply_text += f"\n\n**Câu lệnh SQL do AI tự sinh:**\n```sql\n{chatbot_response['sql']}\n```"
                
            # Append Data Table if present
            data = chatbot_response.get("data")
            cols = chatbot_response.get("columns")
            if data and cols and len(data) > 0:
                table_md = "\n\n| " + " | ".join(cols) + " |\n"
                table_md += "| " + " | ".join(["---"] * len(cols)) + " |\n"
                
                for row in data:
                    row_vals = []
                    for col in cols:
                        val = row.get(col, "")
                        # Format numeric fields like money
                        is_numeric_col = any(keyword in col.lower() for keyword in ["amount", "revenue", "target", "value", "balance", "overdue", "term", "sale"])
                        if isinstance(val, (int, float)) and is_numeric_col:
                            row_vals.append(f"{val:,.0f}")
                        elif val is None:
                            row_vals.append("-")
                        else:
                            row_vals.append(str(val))
                    table_md += "| " + " | ".join(row_vals) + " |\n"
                reply_text += table_md
                
            await turn_context.send_activity(reply_text)
            
        except Exception as e:
            print(f"[Teams Bot Error]: {e}")
            await turn_context.send_activity(f"Rất tiếc, đã xảy ra lỗi trong quá trình xử lý câu hỏi: {str(e)}")

    def _clean_mention(self, text: str) -> str:
        """Removes Microsoft Teams specific mention XML tags."""
        import re
        # Removes tags like <at>Bot Name</at>
        cleaned = re.sub(r'<at>.*?</at>', '', text)
        return cleaned.strip()

# 3. Create global instances
chatbot_instance = DNHChatbot()
dnh_bot = DNHBot(chatbot_instance)
