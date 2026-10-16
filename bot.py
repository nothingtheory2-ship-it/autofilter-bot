import asyncio

# Python Event Loop Fix
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import os
import sys
import ssl
import logging
import threading
import certifi
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client, filters
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO)

# 1. Render Port Binding Server
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Running!")

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# 2. Environment Variables
try:
    API_ID = int(os.environ["API_ID"].strip())
    API_HASH = os.environ["API_HASH"].strip()
    BOT_TOKEN = os.environ["BOT_TOKEN"].strip()
    DATABASE_URI = os.environ["DATABASE_URI"].strip()
    CHANNEL_ID = int(os.environ["CHANNELS"].strip())
    DATABASE_NAME = os.environ.get("DATABASE_NAME", "AutoFilter").strip()
except Exception as e:
    print(f"ERROR: Variable Missing or Invalid Format -> {e}")
    sys.exit(1)

# 3. Custom SSL Context for MongoDB TLS Handshake Fix
ssl_context = ssl.create_default_context(cafile=certifi.where())
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

mongo_client = AsyncIOMotorClient(
    DATABASE_URI,
    tls=True,
    ssl_context=ssl_context
)
db = mongo_client[DATABASE_NAME]
collection = db["files"]

# 4. Telegram Bot Client
app = Client(
    "AutoFilterBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await message.reply_text(
        f"नमस्ते {message.from_user.first_name}!\n\n"
        "बॉट पूरी तरह चालू है। किसी भी फाइल या मूवी का नाम लिखकर भेजें, मैं आपको फ़ाइल ढूँढ कर दूँगा।"
    )

# 5. चैनल की पुरानी सारी फाइलों को इंडेक्स करने की कमांड
@app.on_message(filters.command("index") & filters.private)
async def index_files(client, message):
    msg = await message.reply_text("चैनल की पुरानी फाइल्स को स्कैन किया जा रहा है, कृपया प्रतीक्षा करें...")
    total_saved = 0
    try:
        async for chat_message in client.get_chat_history(CHANNEL_ID):
            media = chat_message.document or chat_message.video or chat_message.audio
            if media and getattr(media, "file_name", None):
                file_name = media.file_name.lower()
                file_data = {
                    "file_name": file_name,
                    "file_id": media.file_id,
                    "caption": chat_message.caption or media.file_name
                }
                await collection.update_one(
                    {"file_name": file_name},
                    {"$set": file_data},
                    upsert=True
                )
                total_saved += 1
        await msg.edit_text(f"इंडेक्सिंग पूरी हुई! कुल {total_saved} फाइल्स डेटाबेस में सेव हो गईं।")
    except Exception as e:
        await msg.edit_text(f"इंडेक्सिंग में समस्या आई: {e}\nसुनिश्चित करें कि बॉट चैनल में Admin है।")

# 6. चैनल में नई फाइल आते ही सेव करना
@app.on_message(filters.chat(CHANNEL_ID) & (filters.document | filters.video | filters.audio))
async def save_channel_files(client, message):
    media = message.document or message.video or message.audio
    if media and getattr(media, "file_name", None):
        file_name = media.file_name.lower()
        file_data = {
            "file_name": file_name,
            "file_id": media.file_id,
            "caption": message.caption or media.file_name
        }
        await collection.update_one(
            {"file_name": file_name},
            {"$set": file_data},
            upsert=True
        )
        print(f"सहेजी गई फाइल: {media.file_name}")

# 7. सर्च और फाइल सेंड करना
@app.on_message(filters.private & filters.text & ~filters.command(["start", "help", "index"]))
async def search_files(client, message):
    query = message.text.lower().strip()
    results = collection.find({"file_name": {"$regex": query, "$options": "i"}}).limit(10)
    
    found = False
    try:
        async for item in results:
            found = True
            await client.send_cached_media(
                chat_id=message.chat.id,
                file_id=item["file_id"],
                caption=item.get("caption", item["file_name"])
            )
    except Exception as e:
        await message.reply_text(f"डेटाबेस एरर: {e}")
        return

    if not found:
        await message.reply_text("माफ़ कीजिए, इस नाम से कोई फाइल नहीं मिली। कृपया सही नाम लिखकर भेजें।")

print(">>> BOT STARTED SUCCESSFULLY! <<<")
app.run()
