# instagram_bot.py
import requests
import random
import string
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# === CONFIG ===
BOT_TOKEN = "8495318163:AAHDMZy-S6lw_XyDhl6E2bF1Wv4_xARczqM"
CHAT_ID = 5923090134
PASSWORD = "000999"
PROXY = "gw.dataimpulse.com:824"

# === FUNCTIONS ===

def random_username():
    return "user" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

def get_temp_email():
    domain = "1secmail.com"
    name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{name}@{domain}", name, domain

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Send /create <count> to create accounts.")

async def create_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /create <number>")
        return

    results = []
    for _ in range(count):
        username = random_username()
        email, name, domain = get_temp_email()

        # --- Simulated Instagram creation ---
        # Replace this part later with real API/browser automation
        results.append(f"{username} | {PASSWORD} | {email}")

    msg = "✅ Accounts Created:\n" + "\n".join(results)
    await context.bot.send_message(chat_id=CHAT_ID, text=msg)

# === MAIN ===
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("create", create_accounts))
    app.run_polling()

if __name__ == "__main__":
    main()
