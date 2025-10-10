from flask import Flask, request
import threading
from aiogram import Bot, Dispatcher, types
import asyncio
import os

TOKEN = os.getenv("BOT_TOKEN")  # Render environment variable orqali
bot = Bot(token=TOKEN)
dp = Dispatcher()

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot ishlayapti ✅"

@app.route('/send', methods=['POST'])
def send_message():
    data = request.json
    user_id = data.get('user_id')
    text = data.get('text')
    asyncio.run(bot.send_message(user_id, text))
    return "Yuborildi", 200

async def start_bot():
    await dp.start_polling(bot)

def run_bot():
    asyncio.run(start_bot())

if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
