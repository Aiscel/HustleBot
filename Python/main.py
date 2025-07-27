
import logging
import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

class HustleBot:
    def __init__(self):
        self.db_path = "hustle_bot.db"
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

# Initialize bot instance
hustle_bot = HustleBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - welcome new users"""
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
    meme_text = """
🎭 MEME SUBMISSION

📸 Send me a photo or GIF to submit a meme!
✨ Add a caption to make it funnier
🏆 Earn 50 hustle points per meme
💎 Best memes get bonus points!

Just send your meme now! 📱
    """
    await update.message.reply_text(meme_text)

async def handle_meme_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo/GIF submissions as memes"""
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
    # Get token from environment variable
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print("❌ Please set TELEGRAM_BOT_TOKEN environment variable")
        print("💡 Add your bot token to environment variables")
        return
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("points", check_points))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("daily", daily_tasks))
    application.add_handler(CommandHandler("submit_meme", submit_meme_command))
    
    # Handle photo submissions as memes
    application.add_handler(MessageHandler(filters.PHOTO, handle_meme_submission))
    
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
