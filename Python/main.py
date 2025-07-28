
import logging
import os
import json
import sqlite3
import re
import hashlib
import random
import string
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple
import asyncio
from collections import defaultdict, deque
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import TelegramError

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global application variable
application = None

class ModerationSystem:
    def __init__(self):
        # Anti-spam settings
        self.flood_limits = {
            'messages_per_minute': 10,
            'commands_per_minute': 5,
            'same_message_limit': 3
        }
        
        # User tracking
        self.user_messages = defaultdict(lambda: deque(maxlen=50))
        self.user_commands = defaultdict(lambda: deque(maxlen=20))
        self.user_warnings = defaultdict(int)
        self.muted_users = set()
        self.banned_users = set()
        
        # Verification system
        self.pending_verification = {}
        self.verified_users = set()
        
        # Spam keywords (expandable)
        self.spam_keywords = {
            'scam': ['airdrop', 'free crypto', 'pump', 'moonshot', 'guaranteed profit', 
                    'double your', 'investment opportunity', 'click here', 'limited time',
                    'dm me', 'telegram.me', 't.me/', 'bit.ly', 'tinyurl'],
            'promo': ['join my channel', 'subscribe', 'follow me', 'check my bio',
                     'promotion', 'advertisement', 'buy now', 'special offer'],
            'raid': ['raid', 'spam', 'flood', 'attack', 'mass message']
        }
        
        # Admin user IDs (set these for your admins)
        self.admin_ids = set()
        
        # Suspicious patterns
        self.suspicious_patterns = [
            r'[a-zA-Z0-9]{20,}',  # Long random strings
            r'(http|https)://[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}',  # URLs
            r'@[a-zA-Z0-9_]{5,}',  # Username mentions
            r'\b\d{10,}\b'  # Long numbers (phone numbers, etc.)
        ]
    
    def add_admin(self, user_id: int):
        """Add admin user"""
        self.admin_ids.add(user_id)
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in self.admin_ids
    
    def is_flood_spam(self, user_id: int, message_text: str) -> bool:
        """Check for flood/spam behavior"""
        now = datetime.now()
        
        # Check message frequency
        user_msgs = self.user_messages[user_id]
        user_msgs.append(now)
        
        # Count messages in last minute
        recent_msgs = [msg for msg in user_msgs if (now - msg).seconds < 60]
        if len(recent_msgs) > self.flood_limits['messages_per_minute']:
            return True
        
        # Check for repeated messages
        recent_text_list = list(user_msgs)[-10:]
        same_count = sum(1 for msg_time in recent_text_list if str(msg_time) == message_text)
        if same_count >= self.flood_limits['same_message_limit']:
            return True
        
        return False
    
    def is_command_spam(self, user_id: int) -> bool:
        """Check for command spam"""
        now = datetime.now()
        user_cmds = self.user_commands[user_id]
        user_cmds.append(now)
        
        # Count commands in last minute
        recent_cmds = [cmd for cmd in user_cmds if (now - cmd).seconds < 60]
        return len(recent_cmds) > self.flood_limits['commands_per_minute']
    
    def contains_spam_keywords(self, text: str) -> Tuple[bool, str]:
        """Check if text contains spam keywords"""
        text_lower = text.lower()
        
        for category, keywords in self.spam_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return True, category
        
        return False, ""
    
    def is_suspicious_pattern(self, text: str) -> bool:
        """Check for suspicious patterns"""
        for pattern in self.suspicious_patterns:
            if re.search(pattern, text):
                return True
        return False
    
    def generate_captcha(self) -> Tuple[str, str]:
        """Generate simple math CAPTCHA"""
        num1 = random.randint(1, 10)
        num2 = random.randint(1, 10)
        question = f"What is {num1} + {num2}?"
        answer = str(num1 + num2)
        return question, answer
    
    def add_warning(self, user_id: int) -> int:
        """Add warning to user and return warning count"""
        self.user_warnings[user_id] += 1
        return self.user_warnings[user_id]
    
    def mute_user(self, user_id: int):
        """Mute user"""
        self.muted_users.add(user_id)
    
    def unmute_user(self, user_id: int):
        """Unmute user"""
        self.muted_users.discard(user_id)
    
    def ban_user(self, user_id: int):
        """Ban user"""
        self.banned_users.add(user_id)
    
    def is_muted(self, user_id: int) -> bool:
        """Check if user is muted"""
        return user_id in self.muted_users
    
    def is_banned(self, user_id: int) -> bool:
        """Check if user is banned"""
        return user_id in self.banned_users

class HustleBot:
    def __init__(self):
        self.db_path = "hustle_bot.db"
        self.moderation = ModerationSystem()
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                hustle_points INTEGER DEFAULT 0,
                daily_streak INTEGER DEFAULT 0,
                last_activity DATE,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Daily tasks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task_type TEXT,
                completed_date DATE,
                points_earned INTEGER,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Memes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                file_id TEXT,
                caption TEXT,
                votes INTEGER DEFAULT 0,
                submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Moderation tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS moderation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                reason TEXT,
                admin_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_verification (
                user_id INTEGER PRIMARY KEY,
                is_verified BOOLEAN DEFAULT FALSE,
                verification_date TIMESTAMP,
                captcha_attempts INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None):
        """Get user from database or create new one"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, hustle_points, daily_streak, last_activity)
                VALUES (?, ?, ?, 0, 0, ?)
            ''', (user_id, username, first_name, datetime.now().date()))
            conn.commit()
            
        conn.close()
        return user
    
    def add_hustle_points(self, user_id: int, points: int):
        """Add hustle points to user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users SET hustle_points = hustle_points + ?, last_activity = ?
            WHERE user_id = ?
        ''', (points, datetime.now().date(), user_id))
        
        conn.commit()
        conn.close()
    
    def get_user_stats(self, user_id: int):
        """Get user statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        conn.close()
        return user
    
    def get_leaderboard(self, limit: int = 10):
        """Get top users by hustle points"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, username, first_name, hustle_points, daily_streak
            FROM users 
            ORDER BY hustle_points DESC 
            LIMIT ?
        ''', (limit,))
        
        leaderboard = cursor.fetchall()
        conn.close()
        return leaderboard
    
    def complete_daily_task(self, user_id: int, task_type: str, points: int):
        """Mark daily task as completed"""
        today = datetime.now().date()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if task already completed today
        cursor.execute('''
            SELECT * FROM daily_tasks 
            WHERE user_id = ? AND task_type = ? AND completed_date = ?
        ''', (user_id, task_type, today))
        
        if cursor.fetchone():
            conn.close()
            return False  # Already completed
        
        # Add task completion
        cursor.execute('''
            INSERT INTO daily_tasks (user_id, task_type, completed_date, points_earned)
            VALUES (?, ?, ?, ?)
        ''', (user_id, task_type, today, points))
        
        # Update user points and streak
        cursor.execute('''
            UPDATE users SET 
                hustle_points = hustle_points + ?,
                daily_streak = daily_streak + 1,
                last_activity = ?
            WHERE user_id = ?
        ''', (points, today, user_id))
        
        conn.commit()
        conn.close()
        return True
    
    def submit_meme(self, user_id: int, file_id: str, caption: str = None):
        """Submit a meme"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO memes (user_id, file_id, caption)
            VALUES (?, ?, ?)
        ''', (user_id, file_id, caption))
        
        conn.commit()
        conn.close()
        
        # Award points for meme submission
        self.add_hustle_points(user_id, 50)
    
    def log_moderation_action(self, user_id: int, action: str, reason: str, admin_id: int = None):
        """Log moderation actions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO moderation_logs (user_id, action, reason, admin_id)
            VALUES (?, ?, ?, ?)
        ''', (user_id, action, reason, admin_id))
        
        conn.commit()
        conn.close()
    
    def set_user_verification(self, user_id: int, verified: bool = True):
        """Set user verification status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_verification (user_id, is_verified, verification_date)
            VALUES (?, ?, ?)
        ''', (user_id, verified, datetime.now() if verified else None))
        
        conn.commit()
        conn.close()
    
    def is_user_verified(self, user_id: int) -> bool:
        """Check if user is verified"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT is_verified FROM user_verification WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result[0] if result else False

# Initialize bot instance
hustle_bot = HustleBot()

async def check_user_permissions(update: Update) -> bool:
    """Check if user is allowed to interact (not banned/muted)"""
    user_id = update.effective_user.id
    
    if hustle_bot.moderation.is_banned(user_id):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return False
    
    if hustle_bot.moderation.is_muted(user_id):
        await update.message.reply_text("🔇 You are currently muted.")
        return False
    
    return True

async def moderate_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check message for spam/violations and take action"""
    user = update.effective_user
    message_text = update.message.text or update.message.caption or ""
    
    # Skip moderation for admins
    if hustle_bot.moderation.is_admin(user.id):
        return True
    
    # Check if user needs verification
    if not hustle_bot.is_user_verified(user.id) and user.id not in hustle_bot.moderation.verified_users:
        await handle_new_user_verification(update, context)
        return False
    
    # Check flood spam
    if hustle_bot.moderation.is_flood_spam(user.id, message_text):
        warnings = hustle_bot.moderation.add_warning(user.id)
        
        if warnings >= 3:
            hustle_bot.moderation.mute_user(user.id)
            hustle_bot.log_moderation_action(user.id, "MUTED", "Flood spam (3 warnings)", None)
            await update.message.reply_text(f"🔇 {user.first_name} has been muted for flood spamming!")
            await notify_admins(f"🚨 User {user.first_name} (@{user.username}) muted for flood spam", context)
        else:
            await update.message.reply_text(f"⚠️ Warning {warnings}/3: Please slow down your messages!")
        
        await update.message.delete()
        return False
    
    # Check spam keywords
    is_spam, spam_type = hustle_bot.moderation.contains_spam_keywords(message_text)
    if is_spam:
        await update.message.delete()
        hustle_bot.log_moderation_action(user.id, "MESSAGE_DELETED", f"Spam keywords: {spam_type}", None)
        await update.message.reply_text(f"🚫 Message deleted: Contains {spam_type} content")
        await notify_admins(f"🚨 Deleted {spam_type} message from {user.first_name} (@{user.username})", context)
        return False
    
    # Check suspicious patterns
    if hustle_bot.moderation.is_suspicious_pattern(message_text):
        await update.message.reply_text("⚠️ Your message contains suspicious patterns. Please contact an admin if this was a mistake.")
        await notify_admins(f"🔍 Suspicious pattern detected from {user.first_name} (@{user.username}): {message_text[:100]}...", context)
    
    return True

async def handle_new_user_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new user verification with CAPTCHA"""
    user = update.effective_user
    
    if user.id in hustle_bot.moderation.pending_verification:
        await update.message.reply_text("⏳ Please complete your verification first!")
        return
    
    # Generate CAPTCHA
    question, answer = hustle_bot.moderation.generate_captcha()
    hustle_bot.moderation.pending_verification[user.id] = {
        'answer': answer,
        'attempts': 0,
        'timestamp': datetime.now()
    }
    
    verification_text = f"""
🛡️ SECURITY VERIFICATION REQUIRED

Welcome {user.first_name}! To prevent spam and raids, please solve this simple math problem:

❓ {question}

Reply with just the number. You have 3 attempts.
    """
    
    await update.message.reply_text(verification_text)

async def notify_admins(message: str, context: ContextTypes.DEFAULT_TYPE):
    """Notify all admins about moderation events"""
    global application
    for admin_id in hustle_bot.moderation.admin_ids:
        try:
            await application.bot.send_message(chat_id=admin_id, text=f"🔰 ADMIN ALERT\n\n{message}")
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

async def handle_verification_attempt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle CAPTCHA verification attempts"""
    user = update.effective_user
    
    if user.id not in hustle_bot.moderation.pending_verification:
        return
    
    verification_data = hustle_bot.moderation.pending_verification[user.id]
    user_answer = update.message.text.strip()
    
    if user_answer == verification_data['answer']:
        # Verification successful
        del hustle_bot.moderation.pending_verification[user.id]
        hustle_bot.moderation.verified_users.add(user.id)
        hustle_bot.set_user_verification(user.id, True)
        
        await update.message.reply_text("""
✅ VERIFICATION SUCCESSFUL!

Welcome to HustleBot! You can now use all features.
Type /start to begin your hustle journey! 💪
        """)
        
        await notify_admins(f"✅ User {user.first_name} (@{user.username}) verified successfully", context)
    
    else:
        # Wrong answer
        verification_data['attempts'] += 1
        
        if verification_data['attempts'] >= 3:
            # Too many failed attempts - ban user
            del hustle_bot.moderation.pending_verification[user.id]
            hustle_bot.moderation.ban_user(user.id)
            hustle_bot.log_moderation_action(user.id, "BANNED", "Failed verification 3 times", None)
            
            await update.message.reply_text("🚫 Verification failed! You have been banned for security reasons.")
            await notify_admins(f"🚫 User {user.first_name} (@{user.username}) banned for failed verification", context)
        
        else:
            remaining = 3 - verification_data['attempts']
            await update.message.reply_text(f"❌ Wrong answer! {remaining} attempts remaining.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - welcome new users"""
    if not await check_user_permissions(update):
        return
    
    user = update.effective_user
    hustle_bot.get_or_create_user(user.id, user.username, user.first_name)
    
    welcome_text = f"""
🚀 Welcome to HustleBot, {user.first_name}! 

💪 Your journey to success starts here!

🔥 Available Commands:
/points - Check your hustle points
/leaderboard - See top hustlers
/daily - Complete daily tasks
/submit_meme - Submit a meme for points
/help - Show all commands

Let's start hustling! 💯
    """
    
    keyboard = [
        [InlineKeyboardButton("💎 Check Points", callback_data="check_points")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")],
        [InlineKeyboardButton("📋 Daily Tasks", callback_data="daily_tasks")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    help_text = """
🤖 HustleBot Commands:

🎯 Basic Commands:
/start - Start your hustle journey
/points - Check your hustle points
/leaderboard - Top 10 hustlers
/daily - View daily tasks
/submit_meme - Submit meme for points

💡 How to earn points:
• Complete daily tasks (+100 points)
• Submit memes (+50 points)
• Maintain daily streaks (bonus points)
• Engage with the community

🔥 Keep hustling every day to climb the leaderboard!
    """
    await update.message.reply_text(help_text)

async def check_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check user's hustle points"""
    user = update.effective_user
    hustle_bot.get_or_create_user(user.id, user.username, user.first_name)
    
    stats = hustle_bot.get_user_stats(user.id)
    if stats:
        points_text = f"""
💎 Your Hustle Stats:

🔥 Hustle Points: {stats[3]}
⚡ Daily Streak: {stats[4]} days
📅 Last Activity: {stats[5]}
🗓️ Joined: {stats[6][:10]}

Keep grinding! 💪
        """
    else:
        points_text = "❌ Error fetching your stats. Try again!"
    
    await update.message.reply_text(points_text)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard"""
    top_users = hustle_bot.get_leaderboard(10)
    
    if not top_users:
        await update.message.reply_text("🏆 No hustlers yet! Be the first!")
        return
    
    leaderboard_text = "🏆 TOP HUSTLERS LEADERBOARD 🏆\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    
    for i, user in enumerate(top_users):
        user_id, username, first_name, points, streak = user
        medal = medals[i] if i < 3 else f"{i+1}."
        name = username if username else first_name
        leaderboard_text += f"{medal} {name}: {points} points (🔥{streak} streak)\n"
    
    keyboard = [
        [InlineKeyboardButton("💎 My Points", callback_data="check_points")],
        [InlineKeyboardButton("📋 Daily Tasks", callback_data="daily_tasks")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(leaderboard_text, reply_markup=reply_markup)

async def daily_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show daily tasks"""
    user = update.effective_user
    hustle_bot.get_or_create_user(user.id, user.username, user.first_name)
    
    tasks_text = """
📋 DAILY HUSTLE TASKS

Complete these tasks to earn points:

🎯 Share Your Goal (+100 points)
💪 Workout Update (+100 points)  
📚 Learning Progress (+100 points)
🧠 Motivational Quote (+50 points)
💼 Business Update (+150 points)

Click buttons below to complete tasks!
    """
    
    keyboard = [
        [InlineKeyboardButton("🎯 Goal Shared", callback_data="task_goal")],
        [InlineKeyboardButton("💪 Workout Done", callback_data="task_workout")],
        [InlineKeyboardButton("📚 Learning", callback_data="task_learning")],
        [InlineKeyboardButton("🧠 Quote", callback_data="task_quote")],
        [InlineKeyboardButton("💼 Business", callback_data="task_business")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(tasks_text, reply_markup=reply_markup)

async def submit_meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Instructions for submitting memes"""
    if not await check_user_permissions(update):
        return
        
    meme_text = """
🎭 MEME SUBMISSION

📸 Send me a photo or GIF to submit a meme!
✨ Add a caption to make it funnier
🏆 Earn 50 hustle points per meme
💎 Best memes get bonus points!

Just send your meme now! 📱
    """
    await update.message.reply_text(meme_text)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin control panel"""
    user = update.effective_user
    
    if not hustle_bot.moderation.is_admin(user.id):
        await update.message.reply_text("🚫 Admin access required!")
        return
    
    admin_text = f"""
🔰 ADMIN CONTROL PANEL

Available Commands:
/add_admin <user_id> - Add admin
/mute <user_id> - Mute user
/unmute <user_id> - Unmute user  
/ban <user_id> - Ban user
/unban <user_id> - Unban user
/warn <user_id> - Warn user
/mod_stats - Moderation statistics
/verify_user <user_id> - Manually verify user

Current Settings:
📊 Messages/min limit: {hustle_bot.moderation.flood_limits['messages_per_minute']}
⚡ Commands/min limit: {hustle_bot.moderation.flood_limits['commands_per_minute']}
🔇 Muted users: {len(hustle_bot.moderation.muted_users)}
🚫 Banned users: {len(hustle_bot.moderation.banned_users)}
    """
    
    await update.message.reply_text(admin_text)

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add admin user"""
    user = update.effective_user
    
    if not hustle_bot.moderation.is_admin(user.id):
        await update.message.reply_text("🚫 Admin access required!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /add_admin <user_id>")
        return
    
    try:
        new_admin_id = int(context.args[0])
        hustle_bot.moderation.add_admin(new_admin_id)
        await update.message.reply_text(f"✅ User {new_admin_id} added as admin!")
        hustle_bot.log_moderation_action(new_admin_id, "ADMIN_ADDED", "Added by admin", user.id)
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID!")

async def mute_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mute user command"""
    user = update.effective_user
    
    if not hustle_bot.moderation.is_admin(user.id):
        await update.message.reply_text("🚫 Admin access required!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /mute <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        hustle_bot.moderation.mute_user(target_user_id)
        hustle_bot.log_moderation_action(target_user_id, "MUTED", "Muted by admin", user.id)
        await update.message.reply_text(f"🔇 User {target_user_id} has been muted!")
        await notify_admins(f"🔇 User {target_user_id} muted by admin {user.first_name}", context)
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID!")

async def ban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban user command"""
    user = update.effective_user
    
    if not hustle_bot.moderation.is_admin(user.id):
        await update.message.reply_text("🚫 Admin access required!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        hustle_bot.moderation.ban_user(target_user_id)
        hustle_bot.log_moderation_action(target_user_id, "BANNED", "Banned by admin", user.id)
        await update.message.reply_text(f"🚫 User {target_user_id} has been banned!")
        await notify_admins(f"🚫 User {target_user_id} banned by admin {user.first_name}", context)
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID!")

async def mod_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show moderation statistics"""
    user = update.effective_user
    
    if not hustle_bot.moderation.is_admin(user.id):
        await update.message.reply_text("🚫 Admin access required!")
        return
    
    stats_text = f"""
📊 MODERATION STATISTICS

🔇 Muted Users: {len(hustle_bot.moderation.muted_users)}
🚫 Banned Users: {len(hustle_bot.moderation.banned_users)}
⚠️ Users with Warnings: {len(hustle_bot.moderation.user_warnings)}
🛡️ Verified Users: {len(hustle_bot.moderation.verified_users)}
⏳ Pending Verification: {len(hustle_bot.moderation.pending_verification)}
🔰 Total Admins: {len(hustle_bot.moderation.admin_ids)}

💬 Message Tracking: {len(hustle_bot.moderation.user_messages)} users
⚡ Command Tracking: {len(hustle_bot.moderation.user_commands)} users
    """
    
    await update.message.reply_text(stats_text)

async def unmute_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unmute user command"""
    user = update.effective_user
    
    if not hustle_bot.moderation.is_admin(user.id):
        await update.message.reply_text("🚫 Admin access required!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /unmute <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        hustle_bot.moderation.unmute_user(target_user_id)
        hustle_bot.log_moderation_action(target_user_id, "UNMUTED", "Unmuted by admin", user.id)
        await update.message.reply_text(f"🔊 User {target_user_id} has been unmuted!")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID!")

async def unban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unban user command"""
    user = update.effective_user
    
    if not hustle_bot.moderation.is_admin(user.id):
        await update.message.reply_text("🚫 Admin access required!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        hustle_bot.moderation.banned_users.discard(target_user_id)
        hustle_bot.log_moderation_action(target_user_id, "UNBANNED", "Unbanned by admin", user.id)
        await update.message.reply_text(f"✅ User {target_user_id} has been unbanned!")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID!")

async def handle_command_rate_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check command rate limiting"""
    user_id = update.effective_user.id
    
    if hustle_bot.moderation.is_admin(user_id):
        return True
    
    if hustle_bot.moderation.is_command_spam(user_id):
        await update.message.reply_text("⚠️ You're using commands too quickly! Please slow down.")
        return False
    
    return True

async def handle_message_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all incoming messages for moderation"""
    user = update.effective_user
    
    # Handle verification attempts
    if user.id in hustle_bot.moderation.pending_verification:
        await handle_verification_attempt(update, context)
        return
    
    # Moderate message
    if not await moderate_message(update, context):
        return
    
    # Continue with normal message processing if needed

async def handle_meme_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo/GIF submissions as memes"""
    if not await check_user_permissions(update):
        return
        
    if not await moderate_message(update, context):
        return
        
    user = update.effective_user
    hustle_bot.get_or_create_user(user.id, user.username, user.first_name)
    
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        
        hustle_bot.submit_meme(user.id, file_id, caption)
        
        success_text = """
🎉 MEME SUBMITTED!

+50 Hustle Points earned! 💎
Your meme has been added to the collection!

Keep the memes coming! 🔥
        """
        
        keyboard = [
            [InlineKeyboardButton("💎 Check Points", callback_data="check_points")],
            [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(success_text, reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    hustle_bot.get_or_create_user(user.id, user.username, user.first_name)
    
    if query.data == "check_points":
        stats = hustle_bot.get_user_stats(user.id)
        if stats:
            points_text = f"💎 Hustle Points: {stats[3]}\n⚡ Daily Streak: {stats[4]} days"
        else:
            points_text = "❌ Error fetching stats"
        await query.edit_message_text(points_text)
        
    elif query.data == "leaderboard":
        top_users = hustle_bot.get_leaderboard(5)
        leaderboard_text = "🏆 TOP 5 HUSTLERS:\n\n"
        
        for i, user_data in enumerate(top_users):
            name = user_data[1] if user_data[1] else user_data[2]
            leaderboard_text += f"{i+1}. {name}: {user_data[3]} points\n"
        
        await query.edit_message_text(leaderboard_text)
        
    elif query.data == "daily_tasks":
        tasks_text = "📋 Click task buttons to complete them!"
        keyboard = [
            [InlineKeyboardButton("🎯 Goal (+100)", callback_data="task_goal")],
            [InlineKeyboardButton("💪 Workout (+100)", callback_data="task_workout")],
            [InlineKeyboardButton("📚 Learning (+100)", callback_data="task_learning")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(tasks_text, reply_markup=reply_markup)
        
    elif query.data.startswith("task_"):
        task_type = query.data.replace("task_", "")
        task_points = {"goal": 100, "workout": 100, "learning": 100, "quote": 50, "business": 150}
        
        if hustle_bot.complete_daily_task(user.id, task_type, task_points.get(task_type, 50)):
            success_text = f"✅ Task completed! +{task_points.get(task_type, 50)} points earned!"
        else:
            success_text = "⚠️ You already completed this task today!"
        
        await query.edit_message_text(success_text)

def main():
    """Start the bot"""
    global application
    
    # Get token from environment variable
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print("❌ Please set TELEGRAM_BOT_TOKEN environment variable")
        print("💡 Add your bot token to environment variables")
        return
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Add command handlers with rate limiting
    async def rate_limited_start(update, context):
        if await handle_command_rate_limit(update, context):
            await start(update, context)
    
    async def rate_limited_help(update, context):
        if await handle_command_rate_limit(update, context):
            await help_command(update, context)
    
    async def rate_limited_points(update, context):
        if await handle_command_rate_limit(update, context):
            await check_points(update, context)
    
    async def rate_limited_leaderboard(update, context):
        if await handle_command_rate_limit(update, context):
            await leaderboard(update, context)
    
    async def rate_limited_daily(update, context):
        if await handle_command_rate_limit(update, context):
            await daily_tasks(update, context)
    
    async def rate_limited_submit_meme(update, context):
        if await handle_command_rate_limit(update, context):
            await submit_meme_command(update, context)
    
    # Basic commands
    application.add_handler(CommandHandler("start", rate_limited_start))
    application.add_handler(CommandHandler("help", rate_limited_help))
    application.add_handler(CommandHandler("points", rate_limited_points))
    application.add_handler(CommandHandler("leaderboard", rate_limited_leaderboard))
    application.add_handler(CommandHandler("daily", rate_limited_daily))
    application.add_handler(CommandHandler("submit_meme", rate_limited_submit_meme))
    
    # Admin commands
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("add_admin", add_admin_command))
    application.add_handler(CommandHandler("mute", mute_user_command))
    application.add_handler(CommandHandler("unmute", unmute_user_command))
    application.add_handler(CommandHandler("ban", ban_user_command))
    application.add_handler(CommandHandler("unban", unban_user_command))
    application.add_handler(CommandHandler("mod_stats", mod_stats_command))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.PHOTO, handle_meme_submission))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_moderation))
    
    # Handle button callbacks
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Check if running on Railway or other platforms (webhook mode)
    port = int(os.getenv('PORT', 5000))
    webhook_url = os.getenv('RAILWAY_STATIC_URL') or os.getenv('RENDER_EXTERNAL_URL')
    
    if webhook_url:
        # Webhook mode for deployment platforms
        print(f"🚀 HustleBot starting in webhook mode on port {port}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=f"{webhook_url}/webhook",
            secret_token=token[:32]  # Use part of bot token as secret
        )
    else:
        # Polling mode for local development
        print("🚀 HustleBot starting in polling mode...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
