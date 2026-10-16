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
import certifi
from pyrogram import Client, filters
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO)

# Environment Variables
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

# MongoDB Connection with SSL Fix
mongo_client = AsyncIOMotorClient(DATABASE_URI, tlsCAFile=certifi.where())
db = mongo_client[DATABASE_NAME]
collection = db["files"]

# Bot Client
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

# Save New Files from Channel to Database
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

# Search and Send Files to Users
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
