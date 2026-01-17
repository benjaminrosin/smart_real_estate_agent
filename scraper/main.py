"""
Main entry point for the Yad2 scraper
"""
import argparse
from dotenv import load_dotenv
from src.scraper import Yad2Scraper
from src.db_manager import MongoDBManager
import src.config as config
import traceback
import requests

# Load environment variables
load_dotenv()

def send_telegram_update(message: str):
    """Send a Telegram message using bot token and chat ID from environment variables"""

    if not config.TELEGRAM_UPDATES_TOKEN or not config.CHAT_ID:
        print("Telegram bot token or chat ID not set in environment variables.")
        return
    
    url = f"https://api.telegram.org/bot{config.TELEGRAM_UPDATES_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.CHAT_ID,
        "text": message
    }
    
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print("Telegram update sent successfully.")
        else:
            print(f"Failed to send Telegram update. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error sending Telegram update: {e}")


def main():
    """Main function to run the scraper"""

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
    
    print("=" * 80)
    print("Yad2 Real Estate Scraper - MongoDB Edition")
    print("=" * 80)
    print(f"Target: Rental properties")
    print(f"Max pages: {args.pages if args.pages else 'All'}")
    print("=" * 80)
    print()
    
    # Connect to MongoDB
    db = MongoDBManager()
    try:
        if not db.connect(collection_name="listings"):
            print("✗ Failed to connect to database. Exiting.")
            send_telegram_update("✗ Scraper failed to connect to database. Exiting.")
            return
        
        send_telegram_update("🚀 Scraper started successfully and connected to database.")

        # Initialize scraper with DB connection
        scraper = Yad2Scraper(db_manager=db)
        
        # Scrape listings (saves to DB page-by-page)
        scraper.scrape_rentals(max_pages=args.pages)
        
        # Cleanup old listings and track removed count
        removed_count = db.cleanup_old_listings(days_threshold=2)
        scraper.total_listings_removed = removed_count
        
        print("\n✓ Scraping session complete!")
        summary_message = scraper._summary_to_string()
        send_telegram_update(summary_message)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Scraping interrupted by user")
        send_telegram_update("⚠️ Scraping interrupted by user.")
        if hasattr(scraper, 'get_summary'):
            scraper._print_summary()
            send_telegram_update(scraper._summary_to_string())
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        send_telegram_update(f"✗ Unexpected error during scraping:\n{e}")
        traceback.print_exc()
    finally:
        # Always disconnect from database
        db.disconnect()


if __name__ == "__main__":
    main()
