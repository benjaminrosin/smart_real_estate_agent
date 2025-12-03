"""
Selenium-based scraper for Yad2 using undetected-chromedriver
"""
import undetected_chromedriver as uc
import time
import random
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .config import (
    RENT_URL, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX,
    PAGE_LOAD_WAIT, HEADLESS, OUTPUT_DIR
)
from .parser import Yad2Parser


class Yad2SeleniumScraper:
    """Scraper for Yad2.co.il using Selenium with undetected-chromedriver"""
    
    def __init__(self, save_html: bool = False, headless: bool = HEADLESS):
        """
        Initialize the Selenium scraper
        
        Args:
            save_html: If True, saves raw HTML of each page for debugging
            headless: Run browser in headless mode
        """
        self.save_html = save_html
        self.headless = headless
        self.driver = None
        
        if self.save_html:
            self.debug_dir = OUTPUT_DIR / "debug_html"
            self.debug_dir.mkdir(exist_ok=True, parents=True)
            self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            print(f"Debug mode: HTML pages will be saved to {self.debug_dir}")
    
    def _init_driver(self):
        """Initialize the undetected Chrome driver"""
        if self.driver is None:
            print("Initializing Chrome driver (this may take a moment)...")
            
            try:
                # Create fresh options each time
                options = uc.ChromeOptions()
                
                if self.headless:
                    options.add_argument('--headless=new')
                
                # Additional options to avoid detection
                options.add_argument('--disable-blink-features=AutomationControlled')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-gpu')
                options.add_argument('--lang=he-IL')
                
                # Random window size to appear more human
                width = random.randint(1280, 1920)
                height = random.randint(800, 1080)
                options.add_argument(f'--window-size={width},{height}')
                
                # Specify Chrome version 142 to match installed Chrome
                self.driver = uc.Chrome(options=options, version_main=142, use_subprocess=True)
                print("✓ Chrome driver ready")
                
            except Exception as e:
                print(f"Error with version 142: {e}")
                print("Trying with automatic version detection...")
                try:
                    # Create new options object for retry
                    options = uc.ChromeOptions()
                    if self.headless:
                        options.add_argument('--headless=new')
                    options.add_argument('--disable-blink-features=AutomationControlled')
                    options.add_argument('--lang=he-IL')
                    
                    self.driver = uc.Chrome(options=options, use_subprocess=True)
                    print("✓ Chrome driver ready")
                except Exception as e2:
                    print(f"Failed to initialize Chrome driver: {e2}")
                    raise
    
    def _get_random_delay(self) -> float:
        """Get a random delay between min and max"""
        return random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
    
    def _save_debug_html(self, html: str, page_num: int = None):
        """Save HTML page for debugging"""
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
    
    def _simulate_human_behavior(self):
        """Simulate human-like behavior on the page"""
        try:
            # Random scroll to simulate reading
            scroll_amount = random.randint(300, 800)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.5, 1.5))
            
            # Scroll back up a bit
            scroll_back = random.randint(100, 300)
            self.driver.execute_script(f"window.scrollBy(0, -{scroll_back});")
            time.sleep(random.uniform(0.3, 0.8))
            
            # Scroll to bottom slowly
            total_height = self.driver.execute_script("return document.body.scrollHeight")
            current_position = 0
            while current_position < total_height:
                scroll_step = random.randint(200, 400)
                current_position += scroll_step
                self.driver.execute_script(f"window.scrollTo(0, {current_position});")
                time.sleep(random.uniform(0.2, 0.5))
            
            # Scroll back to top
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(random.uniform(0.5, 1.0))
            
        except Exception as e:
            print(f"Note: Could not simulate behavior: {e}")
    
    def fetch_page(self, url: str, page_num: int = None) -> Optional[str]:
        """
        Fetch a page using Selenium
        
        Args:
            url: URL to fetch
            page_num: Page number for debug filename
            
        Returns:
            HTML content as string or None if failed
        """
        try:
            self._init_driver()
            
            print(f"Fetching: {url}")
            self.driver.get(url)
            
            # Wait for page to load - wait for feed items to appear
            try:
                WebDriverWait(self.driver, PAGE_LOAD_WAIT).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="item-basic"]'))
                )
            except Exception as e:
                print(f"Note: Timeout waiting for items (may be normal for last page): {e}")
            
            # Additional random wait to appear more human
            time.sleep(random.uniform(2, 4))
            
            # Simulate human scrolling behavior
            self._simulate_human_behavior()
            
            # Check for CAPTCHA
            html = self.driver.page_source
            if 'captcha' in html.lower() or 'challenge' in html.lower():
                print("⚠️  CAPTCHA detected! Waiting longer...")
                time.sleep(random.uniform(30, 60))
                # Try to refresh
                self.driver.refresh()
                time.sleep(random.uniform(5, 10))
                html = self.driver.page_source
            
            # Save HTML for debugging if enabled
            if self.save_html and html:
                self._save_debug_html(html, page_num)
            
            # Random delay before next request (longer delays)
            delay = self._get_random_delay()
            print(f"Waiting {delay:.1f} seconds before next request...")
            time.sleep(delay)
            
            return html
            
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def scrape_page(self, url: str) -> List[Dict]:
        """
        Scrape a single page and extract listings
        
        Args:
            url: URL of the page to scrape
            
        Returns:
            List of property dictionaries
        """
        html = self.fetch_page(url)
        if not html:
            return []
        
        parser = Yad2Parser(html)
        listings = parser.extract_listings()
        
        print(f"Extracted {len(listings)} listings from page")
        return listings
    
    def scrape_multiple_pages(self, start_url: str, max_pages: int = None) -> List[Dict]:
        """
        Scrape multiple pages of listings
        
        Args:
            start_url: Starting URL
            max_pages: Maximum number of pages to scrape (None for all)
            
        Returns:
            List of all property dictionaries from all pages
        """
        all_listings = []
        page_count = 0
        total_pages = None
        
        try:
            # First, get total pages from page 1
            html = self.fetch_page(start_url, page_num=1)
            if html:
                parser = Yad2Parser(html)
                listings = parser.extract_listings()
                all_listings.extend(listings)
                
                total_pages = parser.get_total_pages()
                if total_pages:
                    actual_max = min(max_pages, total_pages) if max_pages else total_pages
                    print(f"Total pages available: {total_pages}, will scrape: {actual_max}")
                
                print(f"Page 1: {len(listings)} listings")
                page_count = 1
            
            # Determine how many pages to scrape
            pages_to_scrape = max_pages
            if total_pages:
                pages_to_scrape = min(max_pages, total_pages) if max_pages else total_pages
            
            # Scrape remaining pages
            for page_num in range(2, (pages_to_scrape or 1) + 1):
                page_count += 1
                print(f"\n--- Scraping page {page_count} ---")
                
                # Build URL with page parameter
                separator = '&' if '?' in start_url else '?'
                page_url = f"{start_url}{separator}page={page_num}"
                
                # Get HTML
                html = self.fetch_page(page_url, page_num=page_num)
                if not html:
                    break
                
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
            
        finally:
            self.close()
    
    def scrape_rentals(self, max_pages: int = None) -> List[Dict]:
        """
        Scrape rental listings from Yad2
        
        Args:
            max_pages: Maximum number of pages to scrape
            
        Returns:
            List of property dictionaries
        """
        return self.scrape_multiple_pages(RENT_URL, max_pages)
    
    def close(self):
        """Close the browser"""
        if self.driver:
            try:
                print("Closing browser...")
                self.driver.quit()
            except Exception as e:
                print(f"Note: Error closing browser (can be ignored): {e}")
            finally:
                self.driver = None
