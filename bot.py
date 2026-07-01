"""
ربات کوییز گیمینگ روزانه
- هر روز سه بار (۱۱ صبح، ۶ عصر، ۱۰ شب به وقت ایران) یک کوییز گیمینگ فارسی در کانال پست می‌کنه
- سوالات از OpenTDB (category=15 -> Video Games) گرفته و با گوگل ترنسلیت ترجمه می‌شن

متغیرهای محیطی (در Railway تنظیم کن):
    BOT_TOKEN   -> توکن ربات از @BotFather
    CHANNEL_ID  -> آیدی کانال، مثل @mychannel یا -1001234567890
"""

import os
import logging
import random
import html
import datetime
import requests
from deep_translator import GoogleTranslator

from telegram.ext import Application, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]


def fetch_gaming_quizzes(amount: int = 1):
    """گرفتن سوال‌های کوییز گیمینگ از OpenTDB (category=15 -> Video Games)."""
    url = "https://opentdb.com/api.php"
    params = {"amount": amount, "category": 15, "type": "multiple"}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("response_code") != 0:
        raise RuntimeError("OpenTDB چیزی برنگرداند، دوباره تلاش کن.")
    return data["results"]


def translate_to_fa(text: str) -> str:
    """ترجمه متن انگلیسی به فارسی. اگر ترجمه شکست بخورد، متن اصلی برگردانده می‌شود."""
    try:
        return GoogleTranslator(source="en", target="fa").translate(text)
    except Exception as e:
        logger.warning(f"ترجمه ناموفق بود، متن اصلی استفاده می‌شود: {e}")
        return text


async def post_quiz(context: ContextTypes.DEFAULT_TYPE):
    """یک کوییز گیمینگ فارسی در کانال پست می‌کند."""
    try:
        questions = fetch_gaming_quizzes(amount=1)
    except Exception as e:
        logger.error(f"خطا در گرفتن کوییز: {e}")
        return

    q = questions[0]
    question_text = html.unescape(q["question"])
    correct = html.unescape(q["correct_answer"])
    incorrect = [html.unescape(a) for a in q["incorrect_answers"]]

    options = incorrect + [correct]
    random.shuffle(options)
    correct_index = options.index(correct)

    # ترجمه سوال و گزینه‌ها به فارسی
    question_text = translate_to_fa(question_text)
    options = [translate_to_fa(opt) for opt in options]

    # محدودیت کاراکتر تلگرام
    question_text = question_text[:290]
    options = [opt[:95] for opt in options]

    await context.bot.send_poll(
        chat_id=CHANNEL_ID,
        question=f"🎮 کوییز گیمینگ: {question_text}",
        options=options,
        type="quiz",
        correct_option_id=correct_index,
        is_anonymous=True,
    )


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    job_queue = application.job_queue

    # ۱۱:۰۰ صبح ایران = 7:30 UTC
    job_queue.run_daily(post_quiz, time=datetime.time(hour=7, minute=30), name="quiz_morning")
    # ۶:۰۰ عصر ایران = 14:30 UTC
    job_queue.run_daily(post_quiz, time=datetime.time(hour=14, minute=30), name="quiz_evening")
    # ۱۰:۰۰ شب ایران = 18:30 UTC
    job_queue.run_daily(post_quiz, time=datetime.time(hour=18, minute=30), name="quiz_night")

    application.run_polling()


if __name__ == "__main__":
    main()
