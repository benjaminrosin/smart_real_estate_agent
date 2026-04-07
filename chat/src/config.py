"""Configuration settings for the Telegram chat bot"""
import os

# Telegram Bot Settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# MongoDB Settings
MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "yad2_scraper")

# Collections
USERS_COLLECTION = "users"
CHAT_HISTORY_COLLECTION = "chat_history"
LISTINGS_COLLECTION = os.getenv("LISTINGS_COLLECTION", "listings")

# Google Gemini Settings
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Search Settings
SEARCH_RESULT_LIMIT = int(os.getenv("SEARCH_RESULT_LIMIT", "3"))
SEARCH_FETCH_LIMIT = int(os.getenv("SEARCH_FETCH_LIMIT", "40"))

# Best-value ranking weights
WEIGHT_BUDGET_FIT = float(os.getenv("WEIGHT_BUDGET_FIT", "0.45"))
WEIGHT_ROOMS_FIT = float(os.getenv("WEIGHT_ROOMS_FIT", "0.25"))
WEIGHT_VALUE_PER_SQM = float(os.getenv("WEIGHT_VALUE_PER_SQM", "0.20"))
WEIGHT_RECENCY = float(os.getenv("WEIGHT_RECENCY", "0.10"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
