import asyncio

# Python Event Loop Fix
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import os
import sys
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client, filters
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO)

# 1. Render Port Binding Fix (Render Web Service को शांत रखने के लिए डमी सर्वर)
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

# 2. Environment Variables पढ़ना
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

# 3. MongoDB Connection (SSL Handshake Error Fix)
mongo_client = AsyncIOMotorClient(
    DATABASE_URI,
    tls=True,
    tlsAllowInvalidCertificates=True
)
db = mongo_client[DATABASE_NAME]
collection = db["files"]

# 4. Bot Client Initialize
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

# चैनल में नई फाइल आते ही MongoDB में सेव करना
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

# यूज़र के सर्च करने पर फाइल भेजना
@app.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
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
