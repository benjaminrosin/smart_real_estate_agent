"""
Main scraper module for Yad2 real estate listings
"""
import requests
import time
import random
import traceback
from typing import List, Dict
from datetime import datetime
import src.config as config
from .parser import Yad2Parser


class Yad2Scraper:
    """Scraper for Yad2.co.il rental property listings"""
    
    def __init__(self, db_manager=None):
        """
        Initialize the scraper
        
        Args:
            db_manager: MongoDBManager instance for saving listings
            save_html: If True, saves raw HTML of each page for debugging
        """
        self.db_manager = db_manager
        self.session = requests.Session()
        self.save_html = config.DEBUG_MODE
        self.last_url = None  # Track last URL for referer header
        self.current_user_agent = random.choice(config.USER_AGENTS)
        self.current_header_preset = 0
        
        # Metrics tracking
        self.total_pages_scraped = 0
        self.total_listings_inserted = 0
        self.total_listings_new = 0
        self.total_listings_updated = 0
        self.total_listings_removed = 0
        self.total_validation_failures = 0
        self.total_captchas_encountered = 0
        self.total_session_rotations = 0
        self.total_elapsed_time_seconds = 0
        self.start_time = None
        
        if self.save_html:
            # Create debug directory
            self.debug_dir = config.OUTPUT_DIR / "debug_html"
            self.debug_dir.mkdir(exist_ok=True, parents=True)
            self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            print(f"Debug mode: HTML pages will be saved to {self.debug_dir}")
    
    def _rotate_session(self, reason: str = "block"):
        """
        Rotate session with fresh headers and User-Agent
        
        Args:
            reason: Reason for rotation (CAPTCHA/403/429)
        """
        # Close old session
        self.session.close()
        
        # Create new session
        self.session = requests.Session()
        
        # Select new User-Agent
        old_ua = self.current_user_agent
        self.current_user_agent = random.choice([ua for ua in config.USER_AGENTS if ua != old_ua])
        
        # Rotate header preset
        self.current_header_preset = (self.current_header_preset + 1) % len(config.HEADER_PRESETS)
        
        # Increment counter
        self.total_session_rotations += 1
        
        print(f"🔄 Session rotated (Reason: {reason}) - Rotation #{self.total_session_rotations}")
    
    def _get_random_user_agent(self) -> str:
        """Get a random user agent from the pool"""
        return random.choice(config.USER_AGENTS)
    
    def _get_random_delay(self) -> float:
        """Get a random delay between min and max"""
        return random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
    
    def fetch_page(self, url: str, page_num: int = None, attempt: int = 1):
        """
        Fetch a page with error handling and block detection
        
        Args:
            url: URL to fetch
            page_num: Page number for logging and debug
            attempt: Current attempt number (1-3)
            
        Returns:
            Tuple of (html, captcha_encountered) or None if failed
        """
        captcha_encountered = False
        
        try:
            # Build headers with current preset and user agent
            headers = config.get_headers(referer=self.last_url, preset_index=self.current_header_preset)
            headers["User-Agent"] = self.current_user_agent
            
            # Make request
            response = self.session.get(url, headers=headers, timeout=config.TIMEOUT)
            
            # Check for blocks
            is_captcha = 'captcha' in response.text.lower() or 'challenge' in response.text.lower()
            is_403 = response.status_code == 403
            is_429 = response.status_code == 429
            
            if is_captcha or is_403 or is_429:
                # Determine block type and delay
                if is_captcha:
                    block_type = "CAPTCHA"
                    self.total_captchas_encountered += 1
                    captcha_encountered = True
                    delays = [60, 90, 120]  # Escalating delays for CAPTCHA
                elif is_403:
                    block_type = "403 Forbidden"
                    delays = [60, 90, 120]
                else:  # 429
                    block_type = "429 Rate Limit"
                    delays = [90, 120, 150]
                
                if attempt < config.MAX_RETRIES_PER_PAGE:
                    # Rotate session
                    self._rotate_session(reason=block_type)
                    
                    # Wait with escalating delay
                    wait_time = delays[attempt - 1]
                    print(f"⚠️  {block_type} detected on page {page_num} (Attempt {attempt}/{config.MAX_RETRIES_PER_PAGE}) - Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    
                    # Retry
                    return self.fetch_page(url, page_num, attempt + 1)
                else:
                    print(f"✗ Max retries reached for page {page_num} after {block_type}")
                    return None
            
            # Check for other HTTP errors
            response.raise_for_status()
            
            html = response.text
            
            # Save HTML for debugging if enabled
            if self.save_html and html:
                self._save_debug_html(html, page_num)
            
            # Update last URL for next referer
            self.last_url = url
            
            return (html, captcha_encountered)
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Network error fetching page {page_num}: {e}")
            
            if attempt < config.MAX_RETRIES:
                wait_time = attempt * 5
                print(f"  Retrying in {wait_time}s... (attempt {attempt}/{config.MAX_RETRIES})")
                time.sleep(wait_time)
                return self.fetch_page(url, page_num, attempt + 1)
            else:
                print(f"✗ Max retries reached for page {page_num}")
                return None
    
    def _save_debug_html(self, html: str, page_num: int = None):
        """
        Save HTML page for debugging
        
        Args:
            html: HTML content to save
            page_num: Page number for filename
        """
        try:
            if page_num:
                filename = f"page_{page_num}_{self.timestamp}.html"
            else:
                filename = f"page_{self.timestamp}.html"
            
            filepath = self.debug_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            
            print(f"Saved HTML to {filepath}")
        except Exception as e:
            print(f"Warning: Could not save debug HTML: {e}")
    
    def scrape_page(self, url: str) -> List[Dict]:
        """
        Scrape a single page and extract listings
        
        Args:
            url: URL of the page to scrape
            
        Returns:
            List of property dictionaries
        """
        result = self.fetch_page(url)
        if not result:
            return []
        
        html, _ = result
        parser = Yad2Parser(html)
        listings = parser.extract_listings()
        
        return listings
    
    def scrape_multiple_pages(self, start_url: str, max_pages: int = None) -> List[Dict]:
        """
        Scrape multiple pages of listings (DEPRECATED - use scrape_rentals instead)
        
        Args:
            start_url: Starting URL
            max_pages: Maximum number of pages to scrape (None for all)
            
        Returns:
            List of all property dictionaries from all pages
        """
        all_listings = []
        page_count = 0
        total_pages = None
        
        # First, get total pages from page 1
        result = self.fetch_page(start_url, page_num=1)
        if result:
            html, _ = result
            parser = Yad2Parser(html)
            total_pages = parser.get_total_pages()
            if total_pages:
                actual_max = min(max_pages, total_pages) if max_pages else total_pages
                print(f"Total pages available: {total_pages}, will scrape: {actual_max}")
        
        # Determine how many pages to scrape
        pages_to_scrape = max_pages
        if total_pages:
            pages_to_scrape = min(max_pages, total_pages) if max_pages else total_pages
        
        # Scrape each page using page parameter
        for page_num in range(1, (pages_to_scrape or 1) + 1):
            page_count += 1
            print(f"\n--- Scraping page {page_count} ---")
            
            # Build URL with page parameter
            if page_num == 1:
                page_url = start_url
            else:
                separator = '&' if '?' in start_url else '?'
                page_url = f"{start_url}{separator}page={page_num}"
            
            # Get HTML
            result = self.fetch_page(page_url, page_num=page_num)
            if not result:
                break
            
            html, _ = result
            # Parse listings
            parser = Yad2Parser(html)
            listings = parser.extract_listings()
            all_listings.extend(listings)
            
            print(f"Total listings so far: {len(all_listings)}")
            
            # Check if we've reached the limit
            if max_pages and page_count >= max_pages:
                print(f"Reached max pages limit ({max_pages})")
                break
        
        print(f"\n=== Scraping complete: {len(all_listings)} total listings from {page_count} pages ===")
        return all_listings
    
    def scrape_rentals(self, start_url: str, max_pages: int = None):
        """
        Scrape rental listings from Yad2 and save to database page-by-page
        
        Args:
            max_pages: Maximum number of pages to scrape
            start_url: URL to start scraping from (default is config.RENT_URL)
            
        Returns:
            None - saves directly to database
        """
        if not self.db_manager:
            raise ValueError("Database manager not provided. Pass db_manager to constructor.")
        
        self.start_time = datetime.now()
        start_url = start_url
        
        # Get total pages from page 1
        print("Fetching first page to determine total pages...")
        page_1_start_time = time.time()
        result = self.fetch_page(start_url, page_num=1)
        if not result:
            print("✗ Failed to fetch first page")
            return
        
        html, page_1_had_captcha = result
        page_1_wait_time = int(time.time() - page_1_start_time)
        
        parser = Yad2Parser(html)
        total_pages = parser.get_total_pages()
        
        # Determine how many pages to scrape
        pages_to_scrape = max_pages
        if total_pages:
            pages_to_scrape = min(max_pages, total_pages) if max_pages else total_pages
            print(f"Total pages available: {total_pages}, will scrape: {pages_to_scrape}")
        
        print(f"\n{'='*80}")
        print(f"Starting scraping session - Target: {pages_to_scrape} pages")
        print(f"{'='*80}\n")
        
        # Scrape each page
        for page_num in range(1, (pages_to_scrape or 1) + 1):
            # Build URL with page parameter
            if page_num == 1:
                page_url = start_url
                # Use already fetched HTML from first page
                current_html = html
                had_captcha = page_1_had_captcha
                wait_time = page_1_wait_time
            else:
                separator = '&' if '?' in start_url else '?'
                page_url = f"{start_url}{separator}page={page_num}"
                
                # Start timing before delay
                page_start_time = time.time()
                
                # Add random delay before fetching
                delay = self._get_random_delay()
                time.sleep(delay)
                
                # Fetch page
                result = self.fetch_page(page_url, page_num=page_num)
                
                if not result:
                    print(f"Page {page_num} | Status: FAILED | Skipping...")
                    continue
                
                current_html, had_captcha = result
                wait_time = int(time.time() - page_start_time)
            
            # Parse listings
            parser = Yad2Parser(current_html)
            listings = parser.extract_listings()
            listings_count = len(listings)
            
            # Determine CAPTCHA status for this page
            captcha_status = "Yes" if had_captcha else "No"
            
            # Insert to database
            try:
                if listings_count > 0:
                    result = self.db_manager.upsert_listings(listings)
                    inserted = result['inserted']
                    updated = result['updated']
                    validation_failed = result.get('validation_failed', 0)
                    total_processed = inserted + updated

                    self.total_listings_inserted += total_processed
                    self.total_listings_new += inserted
                    self.total_listings_updated += updated
                    self.total_validation_failures += validation_failed
                    self.total_pages_scraped += 1
                    
                    # Single-line log
                    print(f"Page {page_num} | Wait: {wait_time}s | Listings: {listings_count} | CAPTCHA: {captcha_status} | New: {inserted} | Updated: {updated} | ValidationFailed: {validation_failed} | Status: OK")
                else:
                    print(f"Page {page_num} | Wait: {wait_time}s | Listings: 0 | CAPTCHA: {captcha_status} | Status: NO_LISTINGS")
                    
            except Exception as e:
                # Log error with stack trace and stop
                print(f"\n{'='*80}")
                print(f"✗ DATABASE INSERT ERROR on Page {page_num}")
                print(f"{'='*80}")
                print(f"Error: {str(e)}")
                print(f"\nStack Trace:")
                print(traceback.format_exc())
                print(f"{'='*80}")
                print(f"Scraper stopped due to database error.")
                print(f"{'='*80}\n")
                return
            
            # Check if we've reached the limit
            if max_pages and page_num >= max_pages:
                break
        
        elapsed_time_seconds = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        self.total_elapsed_time_seconds += elapsed_time_seconds
        
        # Print summary
        self._print_summary()
    
    def get_summary(self) -> Dict:
        """
        Get scraping session summary
        
        Returns:
            Dictionary with session statistics
        """
        avg_listings = self.total_listings_inserted / self.total_pages_scraped if self.total_pages_scraped > 0 else 0
        
        return {
            'total_pages_scraped': self.total_pages_scraped,
            'total_listings_inserted': self.total_listings_inserted,
            'total_listings_new': self.total_listings_new,
            'total_listings_updated': self.total_listings_updated,
            'total_listings_removed': self.total_listings_removed,
            'total_validation_failures': self.total_validation_failures,
            'total_captchas_encountered': self.total_captchas_encountered,
            'total_session_rotations': self.total_session_rotations,
            'elapsed_time_seconds': self.total_elapsed_time_seconds,
            'average_listings_per_page': avg_listings
        }
    
    def _print_summary(self):
        """Print detailed summary of scraping session"""
        summary = self._summary_to_string()
        
        print(f"\n{'='*80}")
        print(summary)
        print(f"{'='*80}\n")

    def _summary_to_string(self) -> str:
        """Convert summary to a formatted string"""
        summary = self.get_summary()
        elapsed_minutes = summary['elapsed_time_seconds'] / 60
        
        return (
            f"Scraping Summary:\n"
            f"- Total Pages Scraped: {summary['total_pages_scraped']}\n"
            f"- Total Listings Processed: {summary['total_listings_inserted']} "
            f"(New: {summary['total_listings_new']}, Updated: {summary['total_listings_updated']})\n"
            f"- Validation Failures: {summary['total_validation_failures']}\n"
            f"- Listings Removed: {summary['total_listings_removed']}\n"
            f"- Average Listings/Page: {summary['average_listings_per_page']:.2f}\n"
            f"- CAPTCHAs Encountered: {summary['total_captchas_encountered']}\n"
            f"- Session Rotations: {summary['total_session_rotations']}\n"
            f"- Total Time Elapsed: {elapsed_minutes:.2f} minutes"
        )

