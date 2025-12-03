"""
Main scraper module for Yad2 real estate listings
"""
import requests
import time
import random
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
from .config import (
    RENT_URL, USER_AGENTS, get_headers, 
    REQUEST_DELAY_MIN, REQUEST_DELAY_MAX, 
    TIMEOUT, MAX_RETRIES, OUTPUT_DIR
)
from .parser import Yad2Parser


class Yad2Scraper:
    """Scraper for Yad2.co.il rental property listings"""
    
    def __init__(self, save_html: bool = False):
        """
        Initialize the scraper
        
        Args:
            save_html: If True, saves raw HTML of each page for debugging
        """
        self.session = requests.Session()
        self.save_html = save_html
        self.last_url = None  # Track last URL for referer header
        
        if self.save_html:
            # Create debug directory
            self.debug_dir = OUTPUT_DIR / "debug_html"
            self.debug_dir.mkdir(exist_ok=True, parents=True)
            self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            print(f"Debug mode: HTML pages will be saved to {self.debug_dir}")
    
    def _get_random_user_agent(self) -> str:
        """Get a random user agent from the pool"""
        return random.choice(USER_AGENTS)
    
    def _get_random_delay(self) -> float:
        """Get a random delay between min and max"""
        return random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
    
    def fetch_page(self, url: str, retry_count: int = 0, page_num: int = None) -> Optional[str]:
        """
        Fetch a page with error handling and retries
        
        Args:
            url: URL to fetch
            retry_count: Current retry attempt
            page_num: Page number for debug filename
            
        Returns:
            HTML content as string or None if failed
        """
        try:
            # Rotate user agent for each request
            user_agent = self._get_random_user_agent()
            
            # Build headers with referer from last URL
            headers = get_headers(referer=self.last_url)
            headers["User-Agent"] = user_agent
            
            print(f"Fetching: {url}")
            response = self.session.get(url, headers=headers, timeout=TIMEOUT)
            response.raise_for_status()
            
            html = response.text
            
            # Check if we got a CAPTCHA page
            if 'captcha' in html.lower() or 'challenge' in html.lower():
                print("⚠️  CAPTCHA detected! Consider:")
                print("   - Using Selenium with undetected-chromedriver")
                print("   - Adding proxy rotation")
                print("   - Increasing delays further")
                if retry_count < MAX_RETRIES:
                    wait_time = (retry_count + 1) * 10  # Longer wait for CAPTCHA
                    print(f"   - Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    return self.fetch_page(url, retry_count + 1, page_num)
            
            # Save HTML for debugging if enabled
            if self.save_html and html:
                self._save_debug_html(html, page_num)
            
            # Update last URL for next referer
            self.last_url = url
            
            # Add random delay to mimic human behavior
            delay = self._get_random_delay()
            print(f"Waiting {delay:.1f} seconds before next request...")
            time.sleep(delay)
            
            return html
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            
            if retry_count < MAX_RETRIES:
                wait_time = (retry_count + 1) * 5
                print(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/{MAX_RETRIES})")
                time.sleep(wait_time)
                return self.fetch_page(url, retry_count + 1, page_num)
            else:
                print(f"Max retries reached for {url}")
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
        
        # First, get total pages from page 1
        html = self.fetch_page(start_url, page_num=1)
        if html:
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
    
    def scrape_rentals(self, max_pages: int = None) -> List[Dict]:
        """
        Scrape rental listings from Yad2
        
        Args:
            max_pages: Maximum number of pages to scrape
            
        Returns:
            List of property dictionaries
        """
        return self.scrape_multiple_pages(RENT_URL, max_pages)
