import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode

from database import init_db, add_or_update_worker, get_all_workers, get_active_workers, delete_worker, toggle_worker_status
from templates import TEMPLATES
from keyboards import main_admin_kb, template_selection_kb, worker_action_kb
from llm_service import ask_agent

load_dotenv()

MASTER_BOT_TOKEN = os.getenv("MASTER_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

master_bot = Bot(token=MASTER_BOT_TOKEN)
dp = Dispatcher()

active_workers = {}

async def safe_send_message(bot: Bot, chat_id: int, text: str):
    """4096 belgilik cheklovni inobatga oluvchi va format xatoliklarini aylanib o'tuvchi yordamchi"""
    max_len = 4000
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        try:
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            # Markdown sintaksisida xatolik bo'lsa oddiy matn holida chiqaradi
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=None)

async def reload_active_workers():
    global active_workers
    for w in active_workers.values():
        try:
            await w["bot"].session.close()
        except Exception:
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
            print(f"[XATO] {w['name']} bot yuklanmadi: {e}")
    print(f"[STATUS] Xotiraga {len(active_workers)} ta faol bot muvaffaqiyatli yuklandi.")

class WorkerAddFSM(StatesGroup):
    role_key = State()
    name = State()
    emoji = State()
    prompt = State()
    token = State()

# --- ADMIN PANEL HANDLERS ---
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def cmd_admin(message: types.Message):
    await message.answer(
        "🏢 **Kompaniya Boshqaruv Paneli (Master Admin)**\n\nIshchilarni sozlash uchun tanlang:",
        reply_markup=main_admin_kb(),
        parse_mode=ParseMode.MARKDOWN
    )

@dp.callback_query(F.data == "admin_home", F.from_user.id == ADMIN_ID)
async def cb_admin_home(call: types.CallbackQuery):
    await call.message.edit_text("🏢 **Kompaniya Boshqaruv Paneli (Master Admin)**", reply_markup=main_admin_kb())

@dp.callback_query(F.data == "list_workers", F.from_user.id == ADMIN_ID)
async def cb_list_workers(call: types.CallbackQuery):
    workers = await get_all_workers()
    if not workers:
        await call.message.edit_text("Hozircha tizimda ishchi botlar yo'q.", reply_markup=main_admin_kb())
        return

    text = "👥 **Jamoangizdagi Ishchilar:**\n\n"
    buttons = []
    for w in workers:
        status = "🟢 Faol" if w["is_active"] else "🔴 To'xtatilgan"
        text += f"{w['emoji']} **{w['name']}** (`{w['role_key']}`) — {status}\n"
        buttons.append([types.InlineKeyboardButton(text=f"⚙️ {w['emoji']} {w['name']}", callback_data=f"manage_{w['id']}")])
    
    buttons.append([types.InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_home")])
    await call.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode=ParseMode.MARKDOWN)

@dp.callback_query(F.data.startswith("manage_"), F.from_user.id == ADMIN_ID)
async def cb_manage_worker(call: types.CallbackQuery):
    worker_id = int(call.data.replace("manage_", ""))
    workers = await get_all_workers()
    worker = next((w for w in workers if w["id"] == worker_id), None)
    if not worker:
        await call.answer("Ishchi topilmadi!", show_alert=True)
        return

    status = "🟢 Faol" if worker["is_active"] else "🔴 To'xtatilgan"
    text = (
        f"⚙️ **Ishchi profili:**\n\n"
        f"Nomi: {worker['emoji']} **{worker['name']}**\n"
        f"Kalit so'z: `{worker['role_key']}`\n"
        f"Holat: {status}\n"
        f"Yo'riqnoma: _{worker['system_prompt'][:100]}..._"
    )
    await call.message.edit_text(text, reply_markup=worker_action_kb(worker_id, worker["is_active"]), parse_mode=ParseMode.MARKDOWN)

@dp.callback_query(F.data.startswith("toggle_"), F.from_user.id == ADMIN_ID)
async def cb_toggle_worker(call: types.CallbackQuery):
    worker_id = int(call.data.replace("toggle_", ""))
    await toggle_worker_status(worker_id)
    await reload_active_workers()
    await call.answer("Holat yangilandi!")
    await cb_list_workers(call)

@dp.callback_query(F.data.startswith("del_"), F.from_user.id == ADMIN_ID)
async def cb_delete_worker(call: types.CallbackQuery):
    worker_id = int(call.data.replace("del_", ""))
    await delete_worker(worker_id)
    await reload_active_workers()
    await call.answer("Ishchi bazadan o'chirildi!", show_alert=True)
    await cb_list_workers(call)

@dp.callback_query(F.data == "add_worker_select", F.from_user.id == ADMIN_ID)
async def cb_add_worker_select(call: types.CallbackQuery):
    await call.message.edit_text("Qaysi kasb shablonini qo'shmoqchisiz?", reply_markup=template_selection_kb())

@dp.callback_query(F.data.startswith("tpl_"), F.from_user.id == ADMIN_ID)
async def cb_template_chosen(call: types.CallbackQuery, state: FSMContext):
    tpl_key = call.data.replace("tpl_", "")
    if tpl_key in TEMPLATES:
        tpl = TEMPLATES[tpl_key]
        await state.update_data(
            role_key=tpl_key,
            name=tpl["name"],
            emoji=tpl["emoji"],
            prompt=tpl["prompt"]
        )
        await call.message.edit_text(
            f"Tanlandi: {tpl['emoji']} **{tpl['name']}**\n\n"
            f"`@BotFather` bergan ushbu botning **Tokenini** yuboring:",
            parse_mode=ParseMode.MARKDOWN
        )
        await state.set_state(WorkerAddFSM.token)

@dp.message(WorkerAddFSM.token, F.from_user.id == ADMIN_ID)
async def process_token_input(message: types.Message, state: FSMContext):
    token = message.text.strip()
    data = await state.get_data()

    await add_or_update_worker(
        name=data["name"],
        role_key=data["role_key"],
        token=token,
        emoji=data["emoji"],
        system_prompt=data["prompt"]
    )
    await reload_active_workers()
    await state.clear()

    await message.answer(
        f"🎉 {data['emoji']} **{data['name']}** muvaffaqiyatli saqlandi va jamoaga qo'shildi!",
        reply_markup=main_admin_kb(),
        parse_mode=ParseMode.MARKDOWN
    )

@dp.callback_query(F.data == "reload_system", F.from_user.id == ADMIN_ID)
async def cb_reload(call: types.CallbackQuery):
    await reload_active_workers()
    await call.answer("Botlar xotirada yangilandi!", show_alert=True)

# --- GROUP TASK PIPELINE ---
@dp.message(Command("task"))
async def handle_team_task(message: types.Message):
    task = message.text.replace("/task", "").strip()
    if not task:
        await message.reply("Topshiriq matnini yozing. Masalan:\n`/task Kriptovalyuta kurslarini kuzatuvchi bot loyihasi`", parse_mode=ParseMode.MARKDOWN)
        return

    if not active_workers:
        await message.reply("Hozircha faol ishchi botlar yo'q. Avval `/admin` orqali ishchi qo'shing.")
        return

    chat_id = message.chat.id
    await message.answer("🚀 **Topshiriq qabul qilindi. Jamoa navbat bilan ish boshlamoqda...**", parse_mode=ParseMode.MARKDOWN)

    for role_key, worker in active_workers.items():
        bot_instance = worker["bot"]
        try:
            status_msg = await bot_instance.send_message(chat_id, f"{worker['emoji']} **[{worker['name']}]**: Bajarilmoqda...", parse_mode=ParseMode.MARKDOWN)
            
            prompt_input = f"Topshiriq: {task}\nO'z kasbing bo'yicha aniq, amaliy va to'liq yechim taqdim et."
            result = await ask_agent(worker["prompt"], prompt_input)
            
            # Eski holat xabarini tozalash
            try:
                await bot_instance.delete_message(chat_id, status_msg.message_id)
            except Exception:
                pass
            
            final_text = f"{worker['emoji']} **[{worker['name']}]**:\n\n{result}"
            await safe_send_message(bot_instance, chat_id, final_text)
            await asyncio.sleep(1.5)
        except Exception as e:
            print(f"[XATO] {worker['name']} bajarishida muammo: {e}")

async def main():
    await init_db()
    await reload_active_workers()
    print("[RUN] Boshliq Bot ishga tushdi...")
    try:
        await dp.start_polling(master_bot)
    finally:
        # Barcha bot sessiyalarini toza yopish
        for w in active_workers.values():
            await w["bot"].session.close()
        await master_bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
