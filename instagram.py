#!/usr/bin/env python3
"""
hybrid_instabot_helper.py
Termux Telegram helper: generates usernames + 1secmail mailboxes, rotates SOCKS5 proxies,
polls mailbox for OTPs, sends prepared account packages to your Telegram.
DOES NOT automate Instagram signup or bypass protections — you must complete signup manually.
"""

import logging
import random
import string
import time
import csv
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler

# ---------------- CONFIG ----------------
BOT_TOKEN = "8495318163:AAHDMZy-S6lw_XyDhl6E2bF1Wv4_xARczqM"   # your bot token
CHAT_ID = "5923090134"                # your numeric chat id
PASSWORD = "000999"                   # password to use for all accounts
EMAIL_DOMAIN = "1secmail.com"
PROXIES = [
    "4eba03e7e13f9aed761c:4ed8de34f304091c@gw.dataimpulse.com:824",
    # Add more proxies if you have them, one per line
]
ACCOUNTS_PER_PROXY = 5     # rotate proxy every this many accounts (default 5)
BATCH_SIZE = 5             # number of accounts to prepare per mailbox/proxy (default 5)
POLL_RETRIES = 30          # how many polling attempts for OTP per mailbox
POLL_DELAY = 2             # seconds between polls

# Conversation state
ASK_NUMBER = 0

# Logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure output files exist
OUTPUT_TXT = "accounts.txt"
OUTPUT_CSV = "accounts.csv"
if not os.path.exists(OUTPUT_CSV):
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["email", "username", "password", "otp", "proxy"])

# ---------- helpers ----------
def randstr(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def gen_username():
    return randstr(8)

def gen_email_address(domain=EMAIL_DOMAIN):
    login = randstr(10)
    return f"{login}@{domain}", login

def make_session_with_socks(proxy_string):
    """proxy_string: 'user:pass@host:port' for socks5"""
    sess = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500,502,503,504])
    sess.mount("https://", HTTPAdapter(max_retries=retries))
    sess.mount("http://", HTTPAdapter(max_retries=retries))
    socks_url = f"socks5h://{proxy_string}"
    sess.proxies.update({"http": socks_url, "https": socks_url})
    sess.headers.update({"User-Agent": "Mozilla/5.0 (Linux; Android 12; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"})
    return sess

def poll_1secmail_for_message(session: requests.Session, login: str, domain: str = EMAIL_DOMAIN, retries=POLL_RETRIES, delay=POLL_DELAY):
    """Poll 1secmail for incoming messages; returns message dict or None"""
    base = "https://www.1secmail.com/api/v1/"
    for i in range(retries):
        try:
            url = f"{base}?action=getMessages&login={login}&domain={domain}"
            r = session.get(url, timeout=12)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and data:
                # read first message details
                msg = data[0]
                read_url = f"{base}?action=readMessage&login={login}&domain={domain}&id={msg['id']}"
                r2 = session.get(read_url, timeout=12)
                r2.raise_for_status()
                return r2.json()
        except Exception:
            pass
        time.sleep(delay)
    return None

def extract_otp_from_message(msg):
    """Extract 4-8 digit code from message body (best effort)"""
    if not msg:
        return None
    body = (msg.get("body") or "") + " " + (msg.get("textBody") or "")
    import re
    m = re.search(r"(\d{4,8})", body)
    return m.group(1) if m else None

def save_account(email, username, password, otp, proxy):
    # append to txt and csv
    with open(OUTPUT_TXT, "a") as f:
        f.write(f"Mail: {email}\nUsername: {username}\nPassword: {password}\nOTP: {otp}\nProxy: {proxy}\n\n")
    with open(OUTPUT_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([email, username, password, otp or "", proxy])

# ---------- Telegram handlers ----------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Hello — send me a number (how many accounts to prepare). Example: '10'\n\n"
        f"I will prepare accounts in batches of {BATCH_SIZE} using each proxy for {ACCOUNTS_PER_PROXY} accounts."
    )
    return ASK_NUMBER

def handle_number(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    chat_id = update.message.chat_id
    if not text.isdigit():
        update.message.reply_text("Please send a positive integer.")
        return ASK_NUMBER
    total = int(text)
    if total <= 0:
        update.message.reply_text("Please send a positive integer greater than zero.")
        return ASK_NUMBER

    update.message.reply_text(f"Preparing {total} account packages. I will send each package to you as it's ready.")
    # run preparation (synchronous)
    created = 0
    proxy_count = len(PROXIES)
    if proxy_count == 0:
        update.message.reply_text("No proxies configured in the script. Edit PROXIES list and restart.")
        return ConversationHandler.END

    while created < total:
        # determine proxy for this batch
        proxy_idx = (created // ACCOUNTS_PER_PROXY) % proxy_count
        proxy_string = PROXIES[proxy_idx]
        sess = make_session_with_socks(proxy_string)

        # per-batch mailbox: create one mailbox to be used for up to BATCH_SIZE accounts
        batch_mail_addr, batch_mail_login = gen_email_address()
        # Inform user which proxy/mail is being used for this batch
        context.bot.send_message(chat_id=chat_id, text=f"Using proxy {proxy_string} and mailbox {batch_mail_addr} for next {BATCH_SIZE} accounts (or remaining).")

        # prepare up to BATCH_SIZE accounts with this mailbox/proxy
        for i in range(min(BATCH_SIZE, total - created)):
            username = gen_username()
            email = batch_mail_addr
            # Note: we do NOT perform Instagram signup programmatically
            # Instead we prepare credentials and poll mailbox for OTP (if any arrives)
            context.bot.send_message(chat_id=chat_id, text=f"Preparing:\nMail: {email}\nUsername: {username}\nPassword: {PASSWORD}\nProxy: {proxy_string}")

            # Poll mailbox for OTP (best-effort)
            msg = poll_1secmail_for_message(sess, batch_mail_login, domain=email.split("@",1)[1], retries=12, delay=3)
            otp = extract_otp_from_message(msg) if msg else None
            if otp:
                context.bot.send_message(chat_id=chat_id, text=f"OTP found for {email}: {otp}")
            else:
                context.bot.send_message(chat_id=chat_id, text=f"OTP: (not received yet for {email}) — finish signup in app and request a new code if needed.")

            # Save the prepared package
            save_account(email, username, PASSWORD, otp, proxy_string)

            created += 1
            time.sleep(1.2)  # small pause between items

    context.bot.send_message(chat_id=chat_id, text=f"Done. Prepared {created} account packages. Saved to {OUTPUT_TXT} and {OUTPUT_CSV}.")
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Cancelled.")
    return ConversationHandler.END

def main():
    if BOT_TOKEN.startswith("YOUR_") or CHAT_ID.startswith("YOUR_"):
        print("Please edit the script and set BOT_TOKEN and CHAT_ID before running.")
        return

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={ASK_NUMBER: [MessageHandler(Filters.text & ~Filters.command, handle_number)]},
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )
    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler('cancel', cancel))

    print("Bot started. Use /start in Telegram to begin.")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
