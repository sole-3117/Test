import os
import asyncio
import aiosqlite
from dotenv import load_dotenv
from google import genai
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

MASTER_BOT_TOKEN = os.getenv("MASTER_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

DB_NAME = "company.db"
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ==================== 1. TAYYOR SHABLONLAR ====================
TEMPLATES = {
    "pm": {
        "name": "Loyiha Menejeri (PM)",
        "emoji": "📋",
        "prompt": "Sen tajribali Project Managersan. Berilgan topshiriqni tahlil qilib, uni aniq bosqichlarga ajratasan va jamoaga tartibli ish rejasini taqdim etasan."
    },
    "ba": {
        "name": "Biznes Tahlilchi (BA)",
        "emoji": "📈",
        "prompt": "Sen Biznes Tahlilchisan. Loyihaning maqsadlari, biznes talablari va foydalanuvchilar ehtiyojlarini aniq qilib belgilab berasan."
    },
    "dev": {
        "name": "Senior Dasturchi",
        "emoji": "💻",
        "prompt": "Sen Senior Backend Dasturchisan. Berilgan vazifa bo'yicha toza kod, arxitektura, ma'lumotlar bazasi va texnik yechimlarni taqdim etasan."
    },
    "qa": {
        "name": "QA Tester / Reviewer",
        "emoji": "🔍",
        "prompt": "Sen Kod Nazoratchisisan. Yechimlarni xatoliklar va xavfsizlik bo'yicha tekshirib, kamchiliklarni ko'rsatasan."
    },
    "devops": {
        "name": "DevOps Muhandisi",
        "emoji": "⚙️",
        "prompt": "Sen DevOps muhandisisan. Server, Docker, deploy va barqarorlik bo'yicha texnik ko'rsatmalar berasan."
    },
    "uiux": {
        "name": "UI/UX Dizayner",
        "emoji": "🎨",
        "prompt": "Sen UI/UX Dizaynersan. Foydalanuvchi qulayligi, interfeys tartibi va ranglar bo'yicha tavsiyalar berasan."
    },
    "copywriter": {
        "name": "Kopirayter / SMM",
        "emoji": "✍️",
        "prompt": "Sen professional Kopiraytersan. E'lonlar, postlar va marketing matnlarini jozibador qilib yozasan."
    },
    "researcher": {
        "name": "Tadqiqotchi Tahlilchi",
        "emoji": "📚",
        "prompt": "Sen Tadqiqotchi va Ma'lumotlar Tahlilchisisan. Faktlarni tekshirasan va chuqur tahliliy xulosa berasan."
    },
    "reporter": {
        "name": "Scrum Master / Hisobotchi",
        "emoji": "📊",
        "prompt": "Sen Scrum Master va Hisobotchisan. Jamoa bajargan ishlarni umumlashtirib, qisqa va aniq hisobot topshirasan."
    }
}

# ==================== 2. MA'LUMOTLAR BAZASI ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role_key TEXT NOT NULL UNIQUE,
                token TEXT NOT NULL,
                emoji TEXT DEFAULT '🤖',
                system_prompt TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        """)
        await db.commit()

async def add_or_update_worker(name: str, role_key: str, token: str, emoji: str, system_prompt: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO workers (name, role_key, token, emoji, system_prompt, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(role_key) DO UPDATE SET
                name=excluded.name,
                token=excluded.token,
                emoji=excluded.emoji,
                system_prompt=excluded.system_prompt,
                is_active=1
        """, (name, role_key, token, emoji, system_prompt))
        await db.commit()

async def get_all_workers():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM workers ORDER BY id ASC") as cursor:
            return await cursor.fetchall()

async def get_active_workers():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM workers WHERE is_active = 1 ORDER BY id ASC") as cursor:
            return await cursor.fetchall()

async def toggle_worker_status(worker_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE workers SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?", (worker_id,))
        await db.commit()

async def delete_worker(worker_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
        await db.commit()

# ==================== 3. AI (GEMINI) XIZMATI ====================
async def ask_agent(system_prompt: str, user_prompt: str) -> str:
    if not client:
        return "Xatolik: GEMINI_API_KEY o'rnatilmagan!"
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=user_prompt,
            config={"system_instruction": system_prompt, "temperature": 0.7}
        )
        return response.text.strip() if response.text else "Javob hosil qilinmadi."
    except Exception as e:
        return f"AI so'rovida xatolik: {e}"

# ==================== 4. TUGMALAR (KEYBOARDS) ====================
def main_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Ishchilar ro'yxati", callback_data="list_workers")],
        [InlineKeyboardButton(text="➕ Yangi ishchi qo'shish", callback_data="add_worker_select")],
        [InlineKeyboardButton(text="🔄 Tizimni yangilash", callback_data="reload_system")]
    ])

def template_selection_kb():
    buttons = []
    for key, data in TEMPLATES.items():
        buttons.append([InlineKeyboardButton(text=f"{data['emoji']} {data['name']}", callback_data=f"tpl_{key}")])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def worker_action_kb(worker_id: int, is_active: int):
    status_btn = "🔴 To'xtatish" if is_active else "🟢 Faollashtirish"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status_btn, callback_data=f"toggle_{worker_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_{worker_id}")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="list_workers")]
    ])

# ==================== 5. ASOSIY BOT LOGIKASI ====================
master_bot = Bot(token=MASTER_BOT_TOKEN)
dp = Dispatcher()
active_workers = {}

async def reload_active_workers():
    global active_workers
    for w in active_workers.values():
        try:
            await w["bot"].session.close()
        except:
            pass
    active_workers.clear()
    
    workers = await get_active_workers()
    for w in workers:
        try:
            active_workers[w["role_key"]] = {
                "bot": Bot(token=w["token"]),
                "name": w["name"],
                "emoji": w["emoji"],
                "prompt": w["system_prompt"]
            }
        except Exception as e:
            print(f"Xatolik {w['name']} yuklanishida: {e}")
    print(f"✅ {len(active_workers)} ta ishchi bot xotiraga yuklandi.")

class WorkerAddFSM(StatesGroup):
    role_key = State()
    name = State()
    emoji = State()
    prompt = State()
    token = State()

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def cmd_admin(message: types.Message):
    await message.answer("🏢 **Kompaniya Boshqaruv Paneli (Master Admin)**", reply_markup=main_admin_kb())

@dp.callback_query(F.data == "admin_home", F.from_user.id == ADMIN_ID)
async def cb_admin_home(call: types.CallbackQuery):
    await call.message.edit_text("🏢 **Kompaniya Boshqaruv Paneli (Master Admin)**", reply_markup=main_admin_kb())

@dp.callback_query(F.data == "list_workers", F.from_user.id == ADMIN_ID)
async def cb_list_workers(call: types.CallbackQuery):
    workers = await get_all_workers()
    if not workers:
        await call.message.edit_text("Hozircha hech qanday ishchi bot qo'shilmagan.", reply_markup=main_admin_kb())
        return
    text = "👥 **Jamoangizdagi Ishchilar:**\n\n"
    buttons = []
    for w in workers:
        status = "🟢 Faol" if w["is_active"] else "🔴 O'chirilgan"
        text += f"{w['emoji']} **{w['name']}** (`{w['role_key']}`) — {status}\n"
        buttons.append([InlineKeyboardButton(text=f"⚙️ {w['emoji']} {w['name']}", callback_data=f"manage_{w['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_home")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("manage_"), F.from_user.id == ADMIN_ID)
async def cb_manage_worker(call: types.CallbackQuery):
    worker_id = int(call.data.replace("manage_", ""))
    workers = await get_all_workers()
    worker = next((w for w in workers if w["id"] == worker_id), None)
    if not worker:
        await call.answer("Ishchi topilmadi!", show_alert=True)
        return
    status = "🟢 Faol" if worker["is_active"] else "🔴 O'chirilgan"
    text = f"⚙️ **{worker['emoji']} {worker['name']}**\nKalit: `{worker['role_key']}`\nHolati: {status}\n"
    await call.message.edit_text(text, reply_markup=worker_action_kb(worker_id, worker["is_active"]))

@dp.callback_query(F.data.startswith("toggle_"), F.from_user.id == ADMIN_ID)
async def cb_toggle_worker(call: types.CallbackQuery):
    worker_id = int(call.data.replace("toggle_", ""))
    await toggle_worker_status(worker_id)
    await reload_active_workers()
    await cb_list_workers(call)

@dp.callback_query(F.data.startswith("del_"), F.from_user.id == ADMIN_ID)
async def cb_delete_worker(call: types.CallbackQuery):
    worker_id = int(call.data.replace("del_", ""))
    await delete_worker(worker_id)
    await reload_active_workers()
    await call.answer("O'chirildi!", show_alert=True)
    await cb_list_workers(call)

@dp.callback_query(F.data == "add_worker_select", F.from_user.id == ADMIN_ID)
async def cb_add_worker_select(call: types.CallbackQuery):
    await call.message.edit_text("Qaysi kasb shablonini qo'shasiz?", reply_markup=template_selection_kb())

@dp.callback_query(F.data.startswith("tpl_"), F.from_user.id == ADMIN_ID)
async def cb_template_chosen(call: types.CallbackQuery, state: FSMContext):
    tpl_key = call.data.replace("tpl_", "")
    if tpl_key in TEMPLATES:
        tpl = TEMPLATES[tpl_key]
        await state.update_data(role_key=tpl_key, name=tpl["name"], emoji=tpl["emoji"], prompt=tpl["prompt"])
        await call.message.edit_text(f"Tanlandi: {tpl['emoji']} **{tpl['name']}**\n\n`@BotFather` bergan tokenni yuboring:")
        await state.set_state(WorkerAddFSM.token)

@dp.message(WorkerAddFSM.token, F.from_user.id == ADMIN_ID)
async def process_token_input(message: types.Message, state: FSMContext):
    token = message.text.strip()
    data = await state.get_data()
    await add_or_update_worker(data["name"], data["role_key"], token, data["emoji"], data["prompt"])
    await reload_active_workers()
    await state.clear()
    await message.answer(f"🎉 {data['emoji']} **{data['name']}** qo'shildi!", reply_markup=main_admin_kb())

@dp.callback_query(F.data == "reload_system", F.from_user.id == ADMIN_ID)
async def cb_reload(call: types.CallbackQuery):
    await reload_active_workers()
    await call.answer("Yangilandi!", show_alert=True)

@dp.message(Command("task"))
async def handle_team_task(message: types.Message):
    task = message.text.replace("/task", "").strip()
    if not task:
        await message.reply("Topshiriq yozing: `/task Kino bot yaratish rejasini tuzing`")
        return
    if not active_workers:
        await message.reply("Faol ishchi botlar yo'q. Avval `/admin` orqali qo'shing.")
        return

    chat_id = message.chat.id
    await message.answer("🚀 **Topshiriq qabul qilindi. Jamoa ishga kirishmoqda...**")

    for role_key, worker in active_workers.items():
        bot_instance = worker["bot"]
        try:
            temp_msg = await bot_instance.send_message(chat_id, f"{worker['emoji']} **[{worker['name']}]**: Bajarmoqdaman...")
            prompt_input = f"Topshiriq: {task}\nO'z sohang bo'yicha aniq, professional yechim tayyorla."
            result = await ask_agent(worker["prompt"], prompt_input)
            await bot_instance.edit_message_text(
                chat_id=chat_id,
                message_id=temp_msg.message_id,
                text=f"{worker['emoji']} **[{worker['name']}]**:\n\n{result}"
            )
            await asyncio.sleep(1.5)
        except Exception as e:
            print(f"Xatolik {worker['name']} xabar yuborishida: {e}")

async def main():
    await init_db()
    await reload_active_workers()
    print("🚀 Boshliq Bot ishga tushdi...")
    await dp.start_polling(master_bot)

if __name__ == "__main__":
    asyncio.run(main())
