import asyncio
import sqlite3
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineQuery, 
    InlineQueryResultArticle, 
    InputTextMessageContent, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiohttp import web

# --- 1. SOZLAMALAR ---
TOKEN = '8628793854:AAHHbKFq3djy3t8HunZYmbrWiG_DxNHvrY0'
ADMIN_ID =  6834542994 

CHANNELS = [
    {"id": -1002480653418, "url": "https://t.me/cinemoshn"},
    {"id": -1003752664553, "url": "https://t.me/seriall_hub"}
]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# --- 2. BAZA BILAN ISHLASH ---
db = sqlite3.connect("kino_bazasi.db")
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS movies (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, file_id TEXT)")
db.commit()

class AddMovie(StatesGroup):
    waiting_for_video = State()
    waiting_for_title = State()

# --- 3. MAJBURIY OBUNANI TEKSHIRISH (YANGILANGAN) ---
async def check_sub(user_id):
    if user_id == ADMIN_ID: return True
    for ch in CHANNELS:
        try:
            m = await bot.get_chat_member(chat_id=ch['id'], user_id=user_id)
            # Agar status 'left' yoki 'kicked' bo'lsa, demak obuna bo'lmagan
            if m.status in ['left', 'kicked']:
                return False
        except Exception as e:
            logging.error(f"Xato: {ch['id']} kanalini tekshirishda muammo: {e}")
            # Agar bot admin bo'lsa-yu, baribir xato bersa, tekshirishni o'tkazib yuboramiz
            continue
    return True

def get_sub_kb():
    buttons = [
        [InlineKeyboardButton(text="📢 1-kanalga obuna bo'lish", url=CHANNELS[0]['url'])],
        [InlineKeyboardButton(text="📢 2-kanalga obuna bo'lish", url=CHANNELS[1]['url'])],
        [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- 4. CALLBACK HANDLER ---
@dp.callback_query(F.data == "check_subscription")
async def check_callback(call: types.CallbackQuery):
    if await check_sub(call.from_user.id):
        await call.answer("✅ Rahmat! Bot ochildi.", show_alert=True)
        await call.message.delete()
        kb = [[InlineKeyboardButton(text="🔍 Kino izlash", switch_inline_query_current_chat="")]]
        await call.message.answer("👋 <b>Xush kelibsiz!</b>\n\nKino izlash uchun pastdagi tugmani bosing:", 
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await call.answer("❌ Hali hamma kanallarga obuna bo'lmadingiz!", show_alert=True)

# --- 5. ADMIN PANEL ---
@dp.message(Command("add"), F.from_user.id == ADMIN_ID)
async def add_start(message: types.Message, state: FSMContext):
    await state.set_state(AddMovie.waiting_for_video)
    await message.answer("📽 <b>Kinoni yuboring:</b>")

@dp.message(AddMovie.waiting_for_video, F.video)
async def process_v(message: types.Message, state: FSMContext):
    await state.update_data(f_id=message.video.file_id)
    await state.set_state(AddMovie.waiting_for_title)
    await message.answer("📝 <b>Kino nomini yozing:</b>")

@dp.message(AddMovie.waiting_for_title)
async def process_t(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute("INSERT INTO movies (title, file_id) VALUES (?, ?)", (message.text.strip(), data['f_id']))
    db.commit()
    await message.answer(f"✅ Qo'shildi! Kodi: <code>{cursor.lastrowid}</code>")
    await state.clear()

# --- 6. INLINE QIDIRUV ---
@dp.inline_query()
async def inline_search(query: InlineQuery):
    if not await check_sub(query.from_user.id):
        return await query.answer([], switch_pm_text="❌ Kanallarga a'zo bo'ling!", switch_pm_parameter="sub")
    s = query.query.strip().lower()
    if not s:
        return await query.answer([], cache_time=1, is_personal=True)

    cursor.execute("SELECT id, title FROM movies WHERE LOWER(title) LIKE ?", (f'%{s}%',))
    rows = cursor.fetchall()
    
    results = []
    for r in rows:
        results.append(
            InlineQueryResultArticle(
                id=f"movie_{r[0]}",
                title=f"🎬 {r[1]}",
                description="Kinoni ko'rish uchun bosing",
                input_message_content=InputTextMessageContent(message_text=str(r[0]))
            )
        )
    await query.answer(results, cache_time=1, is_personal=True)

# --- 7. ASOSIY HANDLER ---
@dp.message()
async def main_handler(message: types.Message):
    if not message.text: return

    # Obunani tekshirish
    if not await check_sub(message.from_user.id):
        await message.answer("❌ <b>Botdan foydalanish uchun kanallarga obuna bo'ling!</b>", 
                             reply_markup=get_sub_kb())
        return

    # Kino kodini tekshirish
    if message.text.isdigit():
        cursor.execute("SELECT title, file_id FROM movies WHERE id = ?", (message.text,))
        movie = cursor.fetchone()
        if movie:
            await bot.send_video(message.chat.id, video=movie[1], caption=f"🎬 <b>{movie[0]}</b>")
            return

    # Start komandasi
    if message.text == "/start":
        kb = [[InlineKeyboardButton(text="🔍 Kino izlash", switch_inline_query_current_chat="")]]
        await message.answer("👋 <b>Xush kelibsiz!</b>\n\nKino izlash uchun pastdagi tugmani bosing.", 
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- 8. RENDER UCHUN WEB SERVER ---
async def handle(request): return web.Response(text="Bot is running!")

async def main():
    # Web serverni ishga tushirish (Render "Failed" bermasligi uchun)
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 10000)))
    await site.start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
