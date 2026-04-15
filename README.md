# Yad2 Real Estate Scraper

A Python web scraper for collecting rental property listings from yad2.co.il.

## Features

- Scrapes rental property listings from Yad2.co.il
- Extracts property details (price, address, rooms, etc.)
- Rate limiting and retry logic for robust scraping
- Saves data Mongo DB
- Configurable page limits

## Usage

### using Docker:
```bash
# Start scraper only
docker compose --profile scraper up -d --build

# Start chat bot only
docker compose --profile chat up -d --build

# Start both services
docker compose --profile all up -d --build
```

### Locally:
#### Install:
1. Activate the virtual environment:
```bash
venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

#### Run:

Basic usage (scrape all pages):
```bash
python main.py
```

Custom options:
```bash
# Scrape 10 pages
python main.py --pages 10
```

## Chat Module (Telegram Bot)

The `chat/` service is a Telegram bot that:

- Registers and manages users (`/start`, `/settings`, `/clear`)
- Uses Gemini through LangChain for conversational responses
- Searches the `listings` collection in MongoDB and returns ranked results

### Chat module requirements

Create `chat/.env` with:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
MONGO_URI=your_mongodb_connection_string
DATABASE_NAME=yad2_scraper
GOOGLE_API_KEY=your_google_api_key

# Optional
GEMINI_MODEL=gemini-2.0-flash
LISTINGS_COLLECTION=listings
SEARCH_RESULT_LIMIT=5
SEARCH_FETCH_LIMIT=40
LOG_LEVEL=INFO
```

### Run chat with Docker

```bash
docker compose --profile chat up -d --build
```

To run both scraper and chat together:

```bash
docker compose --profile all up -d --build
```

### Run chat locally

From the `chat/` folder:

```bash
# 1) Activate your virtual environment
venv\Scripts\activate

# 2) Install dependencies
pip install -r requirements.txt

# 3) Start the bot
python main.py
```

### Telegram commands

- `/start` - register user / greet returning user
- `/settings` - update display name
- `/clear` - clear conversation history

### Schema migration for normalized fields

Run this after pulling parser/schema updates so old listings match the new searchable fields.

From the `scraper` folder:

```bash
# Preview changes only
python migrate_normalized_fields.py --dry-run

# Apply migration to all documents
python migrate_normalized_fields.py

# Optional: migrate only a subset while testing
python migrate_normalized_fields.py --limit 500

# Optional: enforce strict schema validation while migrating
python migrate_normalized_fields.py --strict-validation
```

## Project Structure

```
project/
├── chat/
│   ├── main.py              # Telegram bot entry point
│   ├── requirements.txt     # Chat dependencies
│   ├── Dockerfile           # Chat container build
│   └── src/
│       ├── config.py        # Chat configuration
│       ├── db_manager.py    # User/chat database operations
│       ├── listing_search.py# Rental listing retrieval and ranking
│       └── llm.py           # Gemini + LangChain chat orchestration
├── scraper/
│   ├── main.py              # Scraper entry point
│   ├── requirements.txt     # Scraper dependencies
│   └── src/
│       ├── config.py        # Scraper configuration settings
│       ├── db_manager.py    # Database manager
│       ├── parser.py        # HTML parsing
│       └── scraper.py       # Scraping flow
├── docker-compose.yml       # Multi-service orchestration
├── data/                    # Exported files and debug HTML
└── logs/                    # Runtime logs
```

## Configuration

Edit `scraper/config.py` to adjust:
- Request delay between pages
- Maximum retries
- Default output directory
- User agent and headers

Edit `chat/src/config.py` to adjust:
- Gemini model
- Search limits and ranking weights
- Logging level

## Notes

- The scraper respects rate limits with 30-second delays between requests
- The parser may need adjustments based on Yad2's HTML structure
- The chat module requires valid Telegram, MongoDB, and Google API credentials
