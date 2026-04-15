"""
Main entry point for the Yad2 scraper
"""
import argparse
import logging
import signal
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from src.scraper import Yad2Scraper
from src.db_manager import MongoDBManager
import src.config as config
import requests


def setup_logger() -> tuple[logging.Logger, list[logging.Handler]]:
    """Create a console logger without creating any additional log file."""

    logger = logging.getLogger("yad2_scraper")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)

    logger.addHandler(stream_handler)

    return logger, [stream_handler]


def get_cron_log_file_path() -> Path:
    """Return the daily cron log path (logs/scraper_YYYY-MM-DD.log)."""

    logs_dir = config.PROJECT_ROOT / "logs"
    return logs_dir / f"scraper_{datetime.now().strftime('%Y-%m-%d')}.log"


def send_telegram_update(message: str):
    """Send a Telegram message using bot token and chat ID from environment variables"""

    if not config.TELEGRAM_UPDATES_TOKEN or not config.CHAT_ID:
        print(f"Telegram bot token or chat ID not set in environment variables. {config.TELEGRAM_UPDATES_TOKEN=}, {config.CHAT_ID=}")
        return
    
    url = f"https://api.telegram.org/bot{config.TELEGRAM_UPDATES_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.CHAT_ID,
        "text": message
    }
    
    try:
        response = requests.post(url, data=payload, timeout=15)
        if response.status_code == 200:
            print("Telegram update sent successfully.")
        else:
            print(f"Failed to send Telegram update. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error sending Telegram update: {e}")


def send_telegram_log_file(log_file_path: Path, caption: str):
    """Send a log file to Telegram as a document."""

    if not config.TELEGRAM_UPDATES_TOKEN or not config.CHAT_ID:
        print(
            "Telegram bot token or chat ID not set in environment variables. "
            f"{config.TELEGRAM_UPDATES_TOKEN=}, {config.CHAT_ID=}"
        )
        return

    if not log_file_path.exists():
        send_telegram_update(f"⚠️ Log file not found: {log_file_path}")
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_UPDATES_TOKEN}/sendDocument"
    payload = {
        "chat_id": config.CHAT_ID,
        "caption": caption,
    }

    try:
        with log_file_path.open("rb") as log_file:
            files = {"document": (log_file_path.name, log_file, "text/plain")}
            response = requests.post(url, data=payload, files=files, timeout=30)

        if response.status_code == 200:
            print(f"Telegram log file sent successfully: {log_file_path.name}")
        else:
            print(f"Failed to send Telegram log file. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error sending Telegram log file: {e}")


def install_signal_handlers(logger: logging.Logger):
    """Convert termination signals into KeyboardInterrupt so cleanup runs."""

    def _handle_shutdown_signal(signum, _frame):
        logger.warning(f"Received signal {signum}. Triggering graceful shutdown.")
        raise KeyboardInterrupt("Shutdown signal received")

    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)


def main():
    """Main function to run the scraper"""
    logger, handlers = setup_logger()
    log_file_path = get_cron_log_file_path()
    install_signal_handlers(logger)
    db = MongoDBManager()
    scraper = None

    parser = argparse.ArgumentParser(
        description='Scrape rental property listings from Yad2.co.il and save to MongoDB'
    )
    parser.add_argument(
        '--pages',
        type=int,
        default=config.MAX_PAGES,
        help=f'Maximum number of pages to scrape (default: {config.MAX_PAGES})'
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("Yad2 Real Estate Scraper - MongoDB Edition")
    logger.info("=" * 80)
    logger.info("Target: Rental properties")
    logger.info(f"Max pages: {args.pages if args.pages else 'All'}")
    logger.info("=" * 80)
    
    try:
        if not db.connect(collection_name="listings"):
            raise RuntimeError("Failed to connect to database")
        
        send_telegram_update("🚀 Scraper started successfully and connected to database.")
        logger.info("Connected to MongoDB successfully")

        # Initialize scraper with DB connection
        scraper = Yad2Scraper(db_manager=db)
        total_listings = 0

        for area in config.AREAS:
            logger.info(f"Starting scrape for area: {area}")
            if config.TELEGRAM_VERBOSE_UPDATES:
                send_telegram_update(f"🔍 Starting scrape for area: {area}")
            area_url = f"{config.RENT_URL}/{area}"

            # Scrape listings (saves to DB page-by-page)
            scraper.scrape_rentals(start_url=area_url, max_pages=args.pages)
            
            if config.TELEGRAM_VERBOSE_UPDATES:
                send_telegram_update(f"✅ Completed scrape for area: {area}, total listings for area: {scraper.total_listings_inserted - total_listings}")
                total_listings = scraper.total_listings_inserted

        # Cleanup old listings and track removed count
        removed_count = db.cleanup_old_listings(days_threshold=2)
        scraper.total_listings_removed = removed_count
        
        logger.info("Scraping session complete")
        summary_message = scraper._summary_to_string()
        logger.info(summary_message)
        send_telegram_update(summary_message)
        
    except KeyboardInterrupt:
        logger.warning("Scraping interrupted by user")
        send_telegram_update("⚠️ Scraping interrupted by user.")
        if scraper and hasattr(scraper, 'get_summary'):
            scraper._print_summary()
            send_telegram_update(scraper._summary_to_string())
    except Exception as e:
        logger.exception(f"Unexpected error during scraping: {e}")
        send_telegram_update(f"✗ Unexpected error during scraping:\n{e}")
    finally:
        for handler in handlers:
            try:
                handler.flush()
            except Exception:
                pass

        send_telegram_log_file(
            log_file_path,
            caption=f"Scraper run finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Always disconnect from database
        db.disconnect()

        for handler in handlers:
            try:
                handler.close()
            except Exception:
                pass

        logger.handlers.clear()


if __name__ == "__main__":
    load_dotenv()  # Load environment variables before running main
    main()
