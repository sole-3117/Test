import os
import json
import asyncio
import aiosqlite
from dotenv import load_dotenv
from google import genai
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

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
    
    models_to_try = ["gemini-3.5-flash-lite", "gemini-3.5-flash"]
    last_error = ""
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config={"system_instruction": system_prompt, "temperature": 0.7}
            )
            if response.text:
                return response.text.strip()
        except Exception as e:
            last_error = str(e)
            continue
    return f"AI so'rovida xatolik: {last_error}"

async def smart_triage_task(task_text: str, available_workers: dict) -> dict:
    """Loyiha Menejeri (AI) vazifani tahlil qilib, kimlar kerakligini saralaydi"""
    workers_desc = "\n".join([f"- Kalit: '{k}', Kasbi: '{w['name']}', Tavsifi: '{w['prompt'][:80]}...'" for k, w in available_workers.items()])
    
    triage_prompt = (
        f"Sen Boshqaruvchi Loyiha Menejerisan.\n"
        f"Topshiriq: \"{task_text}\"\n\n"
        f"Mavjud ishchilar:\n{workers_desc}\n\n"
        f"Vazifang:\n"
        f"1. Ushbu topshiriqni bajarish uchun yuqoridagi ishchilardan AYNAN QAYSI BIRI kerakligini aniqla. Keraksiz mutaxassisni umuman tanlama!\n"
        f"2. Har bir tanlangan ishchiga uning sohasiga mos shaxsiy topshiriq yo'riqnomasini (instruction) yoz.\n"
        f"3. Natijani FAQAT quyidagi JSON formatida qaytar (hech qanday qo'shimcha so'zsiz):\n"
        f"{{\n"
        f'  "reasoning": "Topshiriq tahlili va nima uchun ushbu mutaxassislar tanlangani haqida 1-2 jumlalik tushuntirish",\n'
        f'  "plan": [\n'
        f'    {{"role_key": "tanlangan_ishchi_kaliti", "instruction": "Unga beriladigan aniq vazifa"}}\n'
        f'  ]\n'
        f"}}"
    )

    raw_response = await ask_agent("Sen qat'iy JSON formatida javob beruvchi loyiha taqsimlovchi tizimsan.", triage_prompt)
    try:
        # JSON ni tozalab yuklash
        clean_json = raw_response.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception:
        # Agar JSON o'xshamasa, zaxira sifatida hamma ishchilarni qaytaradi
        return {
            "reasoning": "Vazifa barcha mavjud mutaxassislarga yo'naltirildi.",
            "plan": [{"role_key": k, "instruction": task_text} for k in available_workers.keys()]
        }

# ==================== 4. XABARNI BO'LIB YUBORISH ====================
async def send_split_message(bot: Bot, chat_id: int, header: str, content: str, temp_msg_id: int = None):
    full_text = f"{header}\n\n{content}"
    MAX_LEN = 4000
    chunks = [full_text[i:i + MAX_LEN] for i in range(0, len(full_text), MAX_LEN)]

    if temp_msg_id and chunks:
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=temp_msg_id, text=chunks[0])
            chunks = chunks[1:]
        except Exception:
            await bot.send_message(chat_id=chat_id, text=chunks[0])
            chunks = chunks[1:]

    for chunk in chunks:
        await asyncio.sleep(0.5)
        await bot.send_message(chat_id=chat_id, text=chunk)

# ==================== 5. TUGMALAR (KEYBOARDS) ====================
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

# ==================== 6. DISPATCHER VA OB'EKTLAR ====================
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
            b = Bot(token=w["token"])
            bot_info = await b.get_me()
            active_workers[w["role_key"]] = {
                "bot": b,
                "id": bot_info.id,
                "username": bot_info.username,
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

# ==================== 7. BACKUP VA RESTORE ====================
@dp.message(Command("backup"), F.from_user.id == ADMIN_ID)
async def cmd_backup(message: types.Message):
    if not os.path.exists(DB_NAME):
        await message.reply("Baza fayli topilmadi!")
        return
    db_file = FSInputFile(DB_NAME, filename="company_backup.db")
    workers = await get_all_workers()
    await message.answer_document(
        document=db_file,
        caption=f"📦 **Baza Zaxirasi:** {len(workers)} ta ishchi mavjud.\nTiklash uchun ushbu faylga reply qilib `/restore` deb yozing."
    )

@dp.message(Command("restore"), F.from_user.id == ADMIN_ID)
async def cmd_restore(message: types.Message):
    if not message.reply_to_message or not message.reply_to_message.document:
        await message.reply("Faylga reply qilib `/restore` deb yozing.")
        return
    doc = message.reply_to_message.document
    if not doc.file_name.endswith(".db"):
        await message.reply("Faqat `.db` fayl qabul qilinadi!")
        return
    await master_bot.download(doc, destination=DB_NAME)
    await reload_active_workers()
    await message.answer(f"✅ Baza tiklandi! {len(active_workers)} ta ishchi faol.")

@dp.message(F.document, F.from_user.id == ADMIN_ID)
async def handle_db_upload(message: types.Message):
    if message.document.file_name.endswith(".db"):
        await master_bot.download(message.document, destination=DB_NAME)
        await reload_active_workers()
        await message.reply(f"✅ Baza qabul qilindi va tiklandi! ({len(active_workers)} ta ishchi)")

# ==================== 8. ADMIN PANEL ====================
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
        await call.message.edit_text("Hozircha ishchi botlar yo'q.", reply_markup=main_admin_kb())
        return
    text = "👥 **Ishchilar:**\n\n"
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
        await call.answer("Topilmadi!", show_alert=True)
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
        await call.message.edit_text(f"Tanlandi: {tpl['emoji']} **{tpl['name']}**\n\n`@BotFather` tokenini yuboring:")
        await state.set_state(WorkerAddFSM.token)

@dp.message(WorkerAddFSM.token, F.from_user.id == ADMIN_ID)
async def process_token_input(message: types.Message, state: FSMContext):
    token = message.text.strip()
    data = await state.get_data()
    await add_or_update_worker(data["name"], data["role_key"], token, data["emoji"], data["prompt"])
    await reload_active_workers()
    await state.clear()
    await message.answer(f"🎉 {data['emoji']} **{data['name']}** qo'shildi! Yangi bot xabarlarni tinglashi uchun Koyebni bir marta qayta ishga tushiring (Restart).", reply_markup=main_admin_kb())

@dp.callback_query(F.data == "reload_system", F.from_user.id == ADMIN_ID)
async def cb_reload(call: types.CallbackQuery):
    await reload_active_workers()
    await call.answer("Yangilandi!", show_alert=True)

# ==================== 9. HAR BIR ISHCHI BILAN ALOHIDA MULOQOT ====================

@dp.message(F.chat.type == "private")
async def handle_private_worker_chat(message: types.Message, bot: Bot):
    """Foydalanuvchi qaysi ishchi botga shaxsiy chatda yozsa, o'sha bot javob beradi"""
    # Agar xabar Boshliq botga kelgan bo'lsa va bu admin buyrug'i bo'lmasa:
    if bot.token == MASTER_BOT_TOKEN:
        if message.text and not message.text.startswith("/"):
            await message.answer("Men Boshliq Botman. Jamoaga topshiriq berish uchun guruhda `/task` deb yozing yoki sozlash uchun `/admin` buyrug'ini bering.")
        return

    # Agar xabar ishchi botlarning biriga kelgan bo'lsa:
    matched_worker = next((w for w in active_workers.values() if w["bot"].token == bot.token), None)
    if matched_worker:
        wait_msg = await message.answer(f"{matched_worker['emoji']} O'ylayapman...")
        result = await ask_agent(matched_worker["prompt"], message.text)
        await send_split_message(
            bot=bot,
            chat_id=message.chat.id,
            header=f"{matched_worker['emoji']} **{matched_worker['name']}**:",
            content=result,
            temp_msg_id=wait_msg.message_id
        )

# ==================== 10. GURUHDAGI AQLLI TOPSHIRIQ VA TAG QILISH ====================

@dp.message(Command("task"))
async def handle_team_task(message: types.Message):
    """Guruhda aqlli topshiriq berish (Faqat kerakli mutaxassislar jalb qilinadi)"""
    task = message.text.replace("/task", "").strip()
    if not task:
        await message.reply("Topshiriq yozing: `/task Telegram kanalimizga yangi aksiya haqida post yozish kerak`")
        return
    if not active_workers:
        await message.reply("Faol ishchi botlar yo'q.")
        return

    chat_id = message.chat.id
    status_msg = await message.answer("📋 **[Loyiha Menejeri]**: Topshiriq tahlil qilinmoqda...")

    # 1. AI orqali aqlli saralash (Kimlar kerakligini aniqlaymiz)
    triage_result = await smart_triage_task(task, active_workers)
    reasoning = triage_result.get("reasoning", "Topshiriq qabul qilindi.")
    plan = triage_result.get("plan", [])

    # Saralangan mutaxassislarni guruhga e'lon qilamiz
    selected_names = []
    for step in plan:
        k = step["role_key"]
        if k in active_workers:
            selected_names.append(f"{active_workers[k]['emoji']} {active_workers[k]['name']}")

    await status_msg.edit_text(
        f"📋 **[Loyiha Menejeri]**:\n\n"
        f"💡 **Tahlil:** {reasoning}\n"
        f"👥 **Jalb qilingan mas'ullar:** {', '.join(selected_names) if selected_names else 'Hech kim'}\n"
        f"*(Qolgan mutaxassislar bu vazifaga jalb qilinmaydi)*"
    )
    await asyncio.sleep(2)

    # 2. Faqat tanlangan mutaxassislar ketma-ket chiqish qiladi
    for step in plan:
        role_key = step["role_key"]
        instruction = step.get("instruction", task)
        
        if role_key in active_workers:
            worker = active_workers[role_key]
            bot_instance = worker["bot"]
            try:
                temp_msg = await bot_instance.send_message(chat_id, f"{worker['emoji']} **[{worker['name']}]**: Bajarmoqdaman...")
                prompt_input = f"Umumiy kontekst: {task}\nSening aniq vazifang: {instruction}"
                result = await ask_agent(worker["prompt"], prompt_input)
                
                await send_split_message(
                    bot=bot_instance,
                    chat_id=chat_id,
                    header=f"{worker['emoji']} **[{worker['name']}]**:",
                    content=result,
                    temp_msg_id=temp_msg.message_id
                )
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"Xatolik {worker['name']} da: {e}")

@dp.m