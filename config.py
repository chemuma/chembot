# config.py
import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8435664471:AAG743aq1XvwFOPGy_6jU7AV8p21wsiXdQc")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@chemical_eng_uma")
OPERATOR_GROUP_ID = int(os.getenv("OPERATOR_GROUP_ID", "-1002574996302"))
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "5701423397,158893761").split(",")]
CARD_NUMBER = os.getenv("CARD_NUMBER", "6219-8619-2120-2437")
DB_PATH = "/app/data/chemeng_bot.db" 

FEEDBACK_DURATION_HOURS = 48  # مهلت امتیازدهی: 48 ساعت
