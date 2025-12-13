"""
Main entry point for the Yad2 scraper
"""
import argparse
from dotenv import load_dotenv
from scraper import Yad2Scraper
from db_manager import MongoDBManager
from config import MAX_PAGES
import traceback

# Load environment variables
load_dotenv()


def main():
    """Main function to run the scraper"""
    parser = argparse.ArgumentParser(
        description='Scrape rental property listings from Yad2.co.il and save to MongoDB'
    )
    parser.add_argument(
        '--pages',
        type=int,
        default=MAX_PAGES,
        help=f'Maximum number of pages to scrape (default: {MAX_PAGES})'
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
            return
        
        # Initialize scraper with DB connection
        scraper = Yad2Scraper(db_manager=db)
        
        # Scrape listings (saves to DB page-by-page)
        scraper.scrape_rentals(max_pages=args.pages)
        
    
        db.cleanup_old_listings(days_threshold=2)
        
        print("\n✓ Scraping session complete!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Scraping interrupted by user")
        if hasattr(scraper, 'get_summary'):
            scraper._print_summary()
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        traceback.print_exc()
    finally:
        # Always disconnect from database
        db.disconnect()


if __name__ == "__main__":
    main()
