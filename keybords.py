from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from templates import TEMPLATES

def main_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Ishchilar ro'yxati", callback_data="list_workers")],
        [InlineKeyboardButton(text="➕ Yangi ishchi qo'shish", callback_data="add_worker_select")],
        [InlineKeyboardButton(text="🔄 Tizimni qayta yuklash", callback_data="reload_system")]
    ])

def template_selection_kb() -> InlineKeyboardMarkup:
    buttons = []
    for key, data in TEMPLATES.items():
        buttons.append([InlineKeyboardButton(text=f"{data['emoji']} {data['name']}", callback_data=f"tpl_{key}")])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def worker_action_kb(worker_id: int, is_active: int) -> InlineKeyboardMarkup:
    status_btn = "🔴 To'xtatish" if is_active else "🟢 Faollashtirish"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status_btn, callback_data=f"toggle_{worker_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_{worker_id}")],
        [InlineKeyboardButton(text="🔙 Ro'yxatga qaytish", callback_data="list_workers")]
    ]) 
