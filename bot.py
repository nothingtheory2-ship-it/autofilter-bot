import os
import sys
import logging
from pyrogram import Client, filters
from motor.motor_asyncio import AsyncIOMotorClient

# लॉगिंग सेट अप ताकि एरर साफ़ दिखे
logging.basicConfig(level=logging.INFO)

# वेरिएबल्स पढ़ना
try:
    API_ID = int(os.environ["API_ID"].strip())
    API_HASH = os.environ["API_HASH"].strip()
    BOT_TOKEN = os.environ["BOT_TOKEN"].strip()
    DATABASE_URI = os.environ["DATABASE_URI"].strip()
    CHANNEL_ID = int(os.environ["CHANNELS"].strip())
    DATABASE_NAME = os.environ.get("DATABASE_NAME", "AutoFilter").strip()
except Exception as e:
    print(f"ERROR: Variable Missing या गलत फॉर्मेट में है -> {e}")
    sys.exit(1)

# डेटाबेस कनेक्शन
mongo_client = AsyncIOMotorClient(DATABASE_URI)
db = mongo_client[DATABASE_NAME]
collection = db["files"]

# बॉट इनिशियलाइज़
app = Client(
    "AutoFilterBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    await message.reply_text(
        f"नमस्ते {message.from_user.first_name}!\n\n"
        "मैं एक ऑटो-फ़िल्टर बॉट हूँ। मूवी या फाइल का नाम लिखकर भेजें, मैं आपको फ़ाइल ढूँढ कर दूँगा।"
    )

# चैनल में आने वाली नई फाइल्स सेव करना
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
        print(f"फाइल सेव हुई: {media.file_name}")

# यूज़र के मैसेज सर्च करना
@app.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
async def search_files(client, message):
    query = message.text.lower().strip()
    results = collection.find({"file_name": {"$regex": query, "$options": "i"}}).limit(10)
    
    found = False
    async for item in results:
        found = True
        try:
            await client.send_cached_media(
                chat_id=message.chat.id,
                file_id=item["file_id"],
                caption=item.get("caption", item["file_name"])
            )
        except Exception as e:
            await message.reply_text(f"फाइल भेजने में एरर: {e}")

    if not found:
        await message.reply_text("माफ़ कीजिए, इस नाम से कोई फाइल नहीं मिली। कृपया सही नाम लिखकर भेजें।")

print(">>> BOT STARTED SUCCESSFULLY! <<<")
app.run()
