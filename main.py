"""
Main entry point for the Yad2 scraper
"""
import argparse
from dotenv import load_dotenv
from scraper.scraper import Yad2Scraper
from scraper.selenium_scraper import Yad2SeleniumScraper
from scraper.storage import DataStorage
from scraper.db_manager import MongoDBManager
from scraper.config import OUTPUT_DIR, MAX_PAGES, USE_SELENIUM

# Load environment variables
load_dotenv()


def main():
    """Main function to run the scraper"""
    parser = argparse.ArgumentParser(
        description='Scrape rental property listings from Yad2.co.il'
    )
    parser.add_argument(
        '--pages',
        type=int,
        default=MAX_PAGES,
        help=f'Maximum number of pages to scrape (default: {MAX_PAGES})'
    )
    parser.add_argument(
        '--output',
        type=str,
        choices=['csv', 'json', 'both', 'db'],
        default='db',
        help='Output format: csv, json, both, or db (default: db)'
    )
    parser.add_argument(
        '--filename',
        type=str,
        default=None,
        help='Custom output filename (without extension)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Save raw HTML pages for debugging'
    )
    parser.add_argument(
        '--use-selenium',
        action='store_true',
        default=USE_SELENIUM,
        help='Use Selenium with undetected-chromedriver (recommended to bypass CAPTCHA)'
    )
    parser.add_argument(
        '--no-headless',
        action='store_true',
        help='Show browser window (default: headless mode)'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Yad2 Real Estate Scraper")
    print("=" * 60)
    print(f"Target: Rental properties")
    print(f"Max pages: {args.pages if args.pages else 'All'}")
    print(f"Output format: {args.output}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Debug mode: {args.debug}")
    print(f"Using Selenium: {args.use_selenium}")
    if args.use_selenium:
        print(f"Headless mode: {not args.no_headless}")
    print("=" * 60)
    print()
    
    # Initialize scraper and storage
    if args.use_selenium:
        scraper = Yad2SeleniumScraper(save_html=args.debug, headless=not args.no_headless)
    else:
        scraper = Yad2Scraper(save_html=args.debug)
    
    storage = DataStorage(OUTPUT_DIR)
    
    # Scrape listings
    listings = scraper.scrape_rentals(max_pages=args.pages)
    
    if not listings:
        print("\nNo listings found!")
        return
    
    print(f"\nSuccessfully scraped {len(listings)} listings")
    
    # Save data
    print("\nSaving data...")
    if args.output == 'db':
        # Save to MongoDB
        db = MongoDBManager()
        if db.connect(collection_name="listings"):
            inserted_count = db.insert_listings(listings)
            print(f"✓ Saved {inserted_count} listings to database")
            db.disconnect()
        else:
            print("✗ Failed to connect to database")
    elif args.output == 'csv':
        storage.save_to_csv(listings, args.filename)
    elif args.output == 'json':
        storage.save_to_json(listings, args.filename)
    else:  # both
        storage.save_both(listings, args.filename)
    
    print("\n✓ Scraping complete!")


if __name__ == "__main__":
    main()
