"""
ربات تلگرام دو منظوره:
1) زیر هر پست جدید کانال دکمه‌های ریکشن (👍 🔥 ❤️) می‌گذاره و شمارش می‌کنه
2) هر روز در ساعت مشخص ۱ یا ۲ کوییز گیمینگ از OpenTDB می‌گیره و در کانال پست می‌کنه

نیازمندی‌ها (requirements.txt):
    python-telegram-bot==21.4
    requests
    APScheduler

متغیرهای محیطی (در Railway/Render تنظیم کن):
    BOT_TOKEN   -> توکن ربات از @BotFather
    CHANNEL_ID  -> آیدی کانال، مثل @mychannel یا -1001234567890

نکته مهم:
    ربات باید در کانال ادمین باشه با دسترسی "Edit messages" تا بتونه
    دکمه‌های ریکشن رو زیر پست‌های دیگران (نه فقط پست‌های خودش) بگذاره.
"""

import os
import logging
import random
import html
import requests
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]

# شمارش ریکشن‌ها در حافظه: {message_id: {"👍": set(user_ids), ...}}
reactions_store: dict[int, dict[str, set[int]]] = defaultdict(
    lambda: {"👍": set(), "🔥": set(), "❤️": set()}
)

REACTION_EMOJIS = ["👍", "🔥", "❤️"]


def build_reaction_keyboard(message_id: int) -> InlineKeyboardMarkup:
    counts = reactions_store[message_id]
    buttons = [
        InlineKeyboardButton(
            f"{emoji} {len(counts[emoji]) if len(counts[emoji]) > 0 else ''}".strip(),
            callback_data=f"react:{message_id}:{emoji}",
        )
        for emoji in REACTION_EMOJIS
    ]
    return InlineKeyboardMarkup([buttons])


async def on_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی پست جدیدی در کانال منتشر میشه، دکمه‌های ریکشن زیرش گذاشته میشه."""
    msg = update.channel_post
    if msg is None:
        return

    message_id = msg.message_id
    keyboard = build_reaction_keyboard(message_id)

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=msg.chat_id,
            message_id=message_id,
            reply_markup=keyboard,
        )
    except Exception as e:
        # اگر پست توسط خود ربات نباشه و دسترسی ادمین کافی نباشه، اینجا ارور میاد
        logger.warning(f"نتونستم دکمه ریکشن بگذارم: {e}")


async def on_reaction_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی کاربر روی یکی از دکمه‌های ریکشن کلیک می‌کنه."""
    query = update.callback_query
    data = query.data  # فرمت: react:message_id:emoji
    _, message_id_str, emoji = data.split(":")
    message_id = int(message_id_str)
    user_id = query.from_user.id

    counts = reactions_store[message_id]

    # اگر قبلا یک ریکشن دیگه زده، حذفش کن (هر کاربر فقط یک ریکشن فعال داره)
    for e in REACTION_EMOJIS:
        if user_id in counts[e] and e != emoji:
            counts[e].discard(user_id)

    # toggle: اگه همون ایموجی رو دوباره زد، بردارش
    if user_id in counts[emoji]:
        counts[emoji].discard(user_id)
    else:
        counts[emoji].add(user_id)

    keyboard = build_reaction_keyboard(message_id)
    await query.edit_message_reply_markup(reply_markup=keyboard)
    await query.answer()


def fetch_gaming_quizzes(amount: int = 2):
    """گرفتن سوال‌های کوییز گیمینگ از OpenTDB (category=15 -> Video Games)."""
    url = "https://opentdb.com/api.php"
    params = {"amount": amount, "category": 15, "type": "multiple"}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("response_code") != 0:
        raise RuntimeError("OpenTDB چیزی برنگرداند، دوباره تلاش کن.")
    return data["results"]


async def post_daily_quizzes(context: ContextTypes.DEFAULT_TYPE):
    """جاب روزانه: ۲ کوییز گیمینگ در کانال پست می‌کند."""
    try:
        questions = fetch_gaming_quizzes(amount=2)
    except Exception as e:
        logger.error(f"خطا در گرفتن کوییز: {e}")
        return

    for q in questions:
        question_text = html.unescape(q["question"])
        correct = html.unescape(q["correct_answer"])
        incorrect = [html.unescape(a) for a in q["incorrect_answers"]]

        options = incorrect + [correct]
        random.shuffle(options)
        correct_index = options.index(correct)

        # تلگرام پول، حداکثر ۱۰۰ کاراکتر برای هر گزینه و ۳۰۰ برای سوال قبول می‌کنه
        question_text = question_text[:290]
        options = [opt[:95] for opt in options]

        await context.bot.send_poll(
            chat_id=CHANNEL_ID,
            question=f"🎮 کوییز گیمینگ روز: {question_text}",
            options=options,
            type="quiz",
            correct_option_id=correct_index,
            is_anonymous=True,
        )


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        MessageHandler(filters.ChatType.CHANNEL, on_channel_post)
    )
    application.add_handler(
        CallbackQueryHandler(on_reaction_click, pattern=r"^react:")
    )

    # جاب روزانه - ساعت 18:00 به وقت سرور را اینجا تغییر بده (UTC پیش‌فرضه)
    job_queue = application.job_queue
    job_queue.run_daily(
        post_daily_quizzes,
        time=__import__("datetime").time(hour=6, minute=30),  # 10:00 صبح ایران (UTC+3:30)
    )

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
