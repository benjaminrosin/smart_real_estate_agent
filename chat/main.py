"""
Telegram Chat Bot for Real Estate Agent
Handles user registration, settings, and message responses
"""
import logging
from typing import Any, Dict, List

import telebot
from telebot import custom_filters
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StatePickleStorage
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables FIRST before importing config
load_dotenv()

from src import config
from src.db_manager import UserDBManager
from src import llm


def _setup_logging() -> None:
    """Configure application-wide logging once at startup."""
    level_name = config.LOG_LEVEL if config.LOG_LEVEL in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "INFO"
    log_level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


_setup_logging()
logger = logging.getLogger(__name__)

# Validate required environment variables
if not config.TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
if not config.MONGO_URI:
    raise ValueError("MONGO_URI environment variable is required")

# Initialize state storage with persistent pickle file
state_file = Path(__file__).parent / ".bot_states.pkl"
state_storage = StatePickleStorage(file_path=str(state_file))

# Initialize bot with state storage
bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN, state_storage=state_storage)

# Initialize database manager
db = UserDBManager(config.MONGO_URI, config.DATABASE_NAME)

# Per-chat cache for paging through the latest search results.
LISTING_NEXT_CALLBACK = "listing_next"
search_cards_cache: Dict[int, Dict[str, Any]] = {}

# Add custom filters for state handling (MUST be before handler decorators)
bot.add_custom_filter(custom_filters.StateFilter(bot))


# Define states for settings flow
class SettingsStates(StatesGroup):
    waiting_for_name = State()


# ============== Command Handlers ==============

@bot.message_handler(commands=['start'])
def handle_start(message):
    """Handle /start command - register user"""
    chat_id = message.chat.id
    first_name = message.from_user.first_name or "User"
    last_name = message.from_user.last_name
    username = message.from_user.username
    
    # Register user in database
    user = db.register_user(chat_id, first_name, last_name, username)
    display_name = user.get("display_name", first_name)
    
    # Check if new or returning user
    if user.get("registered_at") == user.get("last_seen"):
        welcome_text = (
            f"👋 Welcome, {display_name}!\n\n"
            f"I'm your smart real estate assistant. I can help you find rental properties in Israel.\n\n"
            f"Just tell me what you're looking for!\n\n"
            f"Commands:\n"
            f"/settings - Update your profile\n"
            f"/clear - Clear conversation history"
        )
    else:
        welcome_text = f"👋 Welcome back, {display_name}!\n\nHow can I help you today?"
    
    bot.send_message(chat_id, welcome_text)


@bot.message_handler(commands=['clear'])
def handle_clear(message):
    """Handle /clear command - clear conversation history"""
    chat_id = message.chat.id
    llm.clear_history(str(chat_id))
    search_cards_cache.pop(chat_id, None)
    bot.send_message(chat_id, "🗑️ Conversation history cleared! Let's start fresh.")


@bot.message_handler(commands=['settings'])
def handle_settings(message):
    """Handle /settings command - show settings menu"""
    chat_id = message.chat.id
    
    # Check if user is registered
    user = db.get_user(chat_id)
    if not user:
        bot.send_message(chat_id, "Please use /start to register first.")
        return
    
    display_name = user.get("display_name", user.get("first_name", "User"))
    
    # Create inline keyboard with settings options
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    btn_change_name = telebot.types.InlineKeyboardButton(
        text=f"✏️ Change Name (current: {display_name})",
        callback_data="settings_change_name"
    )
    markup.add(btn_change_name)
    
    bot.send_message(
        chat_id,
        "⚙️ *Settings*\n\nSelect an option to update:",
        reply_markup=markup,
        parse_mode="Markdown"
    )


# ============== Callback Handlers ==============

@bot.callback_query_handler(func=lambda call: call.data == "settings_change_name")
def handle_change_name_callback(call):
    """Handle 'Change Name' button press"""
    chat_id = call.message.chat.id
    
    # Answer callback to remove loading state
    bot.answer_callback_query(call.id)
    
    # Set state to waiting for name input
    bot.set_state(call.from_user.id, SettingsStates.waiting_for_name, chat_id)
    
    logger.debug("State set waiting_for_name user_id=%s chat_id=%s", call.from_user.id, chat_id)
    
    # Ask for new name
    bot.send_message(
        chat_id,
        "📝 Please enter your new display name:\n\n(or send /cancel to cancel)"
    )


@bot.callback_query_handler(func=lambda call: call.data == LISTING_NEXT_CALLBACK)
def handle_next_listing_callback(call):
    """Send the next listing card from the last cached search results."""
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)

    cache = search_cards_cache.get(chat_id)
    if not cache:
        bot.send_message(chat_id, "אין כרגע תוצאות שמורות. אפשר לשלוח שוב בקשת חיפוש.")
        return

    cards = cache.get("cards") or []
    next_index = int(cache.get("next_index", 0))
    if next_index >= len(cards):
        bot.send_message(chat_id, "הצגתי את כל האפשרויות שיש כרגע. רוצה שאחפש עם סינון קצת אחר?")
        return

    _send_listing_card(chat_id, cards[next_index], next_index + 1, len(cards))
    cache["next_index"] = next_index + 1


# ============== State Handlers ==============

@bot.message_handler(state="*")
def handle_any_state(message):
    """Debug: catch all state messages"""
    current_state = bot.get_state(message.from_user.id, message.chat.id)
    logger.debug(
        "State handler message user_id=%s chat_id=%s state=%s text_excerpt=%s",
        message.from_user.id,
        message.chat.id,
        current_state,
        (message.text or "")[:140],
    )
    
    # Check if this is the waiting_for_name state
    if str(current_state) == str(SettingsStates.waiting_for_name):
        handle_name_input_logic(message)
    

def handle_name_input_logic(message):
    """Handle name input when in waiting_for_name state"""
    logger.debug("Name input handler called user_id=%s", message.from_user.id)
    
    chat_id = message.chat.id
    if not message.text:
        bot.send_message(chat_id, "⚠️ Please send a text name, or /cancel to cancel.")
        return

    new_name = message.text.strip()
    
    # Handle cancel
    if new_name.lower() == "/cancel":
        bot.delete_state(message.from_user.id, chat_id)
        bot.send_message(chat_id, "❌ Cancelled. Your name was not changed.")
        return
    
    # Validate name
    if len(new_name) < 1 or len(new_name) > 50:
        bot.send_message(chat_id, "⚠️ Name must be between 1 and 50 characters. Please try again:")
        return
    
    # Update name in database
    success = db.update_user(chat_id, {"display_name": new_name})
    
    # Clear state
    bot.delete_state(message.from_user.id, chat_id)
    
    if success:
        bot.send_message(chat_id, f"✅ Your name has been updated to: <b>{new_name}</b>", parse_mode="HTML")
    else:
        bot.send_message(chat_id, "❌ Failed to update name. Please try again later.")


def _build_next_button_markup(has_more: bool) -> Any:
    if not has_more:
        return None
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(telebot.types.InlineKeyboardButton(text="להצעה הבאה", callback_data=LISTING_NEXT_CALLBACK))
    return markup


def _send_listing_card(chat_id: int, card: Dict[str, Any], index: int, total: int) -> None:
    caption = str(card.get("caption") or "")
    image_url = card.get("image_url")
    has_more = index < total
    markup = _build_next_button_markup(has_more)

    if image_url:
        try:
            bot.send_photo(chat_id, image_url, caption=caption[:1024], parse_mode="HTML", reply_markup=markup)
            return
        except Exception as e:
            logger.warning("Photo send failed, fallback to text chat_id=%s error=%s", chat_id, str(e))

    if caption:
        try:
            bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, caption, reply_markup=markup)


# ============== Default Message Handler ==============

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Handle all other messages with AI"""
    chat_id = message.chat.id
    
    # Check if user has an active state - if so, skip this handler
    current_state = bot.get_state(message.from_user.id, chat_id)
    if current_state is not None:
        return
    
    # Check if user is registered
    user = db.get_user(chat_id)
    if not user:
        bot.send_message(chat_id, "👋 Hi! Please use /start to register first.")
        return
    
    # Show typing indicator while AI processes
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        # Get AI response with conversation history
        response = llm.chat(str(chat_id), message.text)

        def _send_html_chunks(text: str) -> None:
            if not text:
                return
            if len(text) > 4096:
                for i in range(0, len(text), 4096):
                    chunk = text[i:i + 4096]
                    try:
                        bot.send_message(chat_id, chunk, parse_mode="HTML")
                    except Exception:
                        bot.send_message(chat_id, chunk)
            else:
                try:
                    bot.send_message(chat_id, text, parse_mode="HTML")
                except Exception as e:
                    bot.send_message(chat_id, text)
                    logger.warning("HTML parse/send failed, sent plain text chat_id=%s error=%s", chat_id, str(e))

        text = str(response.get("text", "")) if isinstance(response, dict) else str(response)
        primary_listing = response.get("primary_listing") if isinstance(response, dict) else None
        listing_cards = response.get("listing_cards", []) if isinstance(response, dict) else []

        # Cache current search cards so the next button can page through them.
        if listing_cards:
            search_cards_cache[chat_id] = {"cards": listing_cards, "next_index": 1}
        else:
            search_cards_cache.pop(chat_id, None)

        # Send one rich listing card (photo + formatted link) when available.
        if isinstance(primary_listing, dict):
            total = len(listing_cards) if listing_cards else 1
            _send_listing_card(chat_id, primary_listing, 1, total)
            # Avoid sending an additional summary message when a card is shown.
            return

        _send_html_chunks(text)
            
    except Exception as e:
        logger.exception("LLM handler error chat_id=%s error=%s", chat_id, str(e))
        bot.send_message(chat_id, "❌ Sorry, I couldn't process that. Please try again.")


def main():
    """Main function to run the bot"""
    logger.info("Bot starting")
    
    # Connect to database at startup
    logger.info("Connecting to MongoDB")
    if not db.connect(config.USERS_COLLECTION):
        logger.error("Failed to connect to database. Exiting")
        return
    
    try:
        # Start polling with auto-reconnect
        logger.info("Starting polling")
        bot.infinity_polling(timeout=30, long_polling_timeout=30, skip_pending=True)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception("Bot runtime error error=%s", str(e))
    finally:
        db.disconnect()


if __name__ == "__main__":
    main()