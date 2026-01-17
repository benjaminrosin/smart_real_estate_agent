"""
Configuration settings for the Yad2 scraper
"""
import os
from pathlib import Path

# Telegram updates bot settings
TELEGRAM_UPDATES_TOKEN = os.getenv("TELEGRAM_UPDATES_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Base URL
BASE_URL = "https://www.yad2.co.il"
RENT_URL = f"{BASE_URL}/realestate/rent"

# User agents to rotate (appear as different browsers)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

# Header preset variations for rotation
HEADER_PRESETS = [
    {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "DNT": "1"
    },
    {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,he-IL;q=0.8,he;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "no-cache"
    },
    {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "DNT": "0"
    }
]

# Request settings
def get_headers(referer: str = None, preset_index: int = 0):
    """Generate headers with optional referer and preset selection"""
    headers = HEADER_PRESETS[preset_index % len(HEADER_PRESETS)].copy()
    if referer:
        headers["Referer"] = referer
    return headers

# Rate limiting
REQUEST_DELAY_MIN = 30  # minimum seconds between requests
REQUEST_DELAY_MAX = 60  # maximum seconds between requests
TIMEOUT = 30  # request timeout in seconds
MAX_RETRIES = 3  # retries for network errors
MAX_RETRIES_PER_PAGE = 3  # max attempts per page for CAPTCHA/403/429

# Selenium settings
USE_SELENIUM = False  # Use Selenium instead of requests to bypass CAPTCHA
HEADLESS = True  # Run browser in headless mode (no GUI)
PAGE_LOAD_WAIT = 5  # seconds to wait for page to load
SCROLL_BEHAVIOR = True  # Scroll page to simulate human behavior
MOUSE_MOVEMENT = True  # Simulate random mouse movements

# Output settings
DEBUG_MODE = False  # Save raw HTML of pages for debugging
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

# Scraping settings
MAX_PAGES = None  # Maximum number of pages to scrape (set to None for all)
