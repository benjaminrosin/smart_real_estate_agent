"""
HTML parser for extracting property data from Yad2 pages
"""
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import re


class Yad2Parser:
    """Parser for Yad2.co.il rental listings"""
    
    def __init__(self, html: str):
        """
        Initialize parser with HTML content
        
        Args:
            html: Raw HTML string from the page
        """
        self.soup = BeautifulSoup(html, 'lxml')
    
    def extract_listings(self) -> List[Dict]:
        """
        Extract all property listings from the page
        
        Returns:
            List of dictionaries containing property data
        """
        listings = []
        
        # Find all listing items using data-testid="item-basic"
        items = self.soup.find_all(attrs={"data-testid": "item-basic"})
        
        print(f"Found {len(items)} property listings")
        
        for item in items:
            try:
                listing_data = self._extract_listing_data(item)
                if listing_data:
                    listings.append(listing_data)
            except Exception as e:
                print(f"Error parsing listing: {e}")
                continue
        
        return listings
    
    def _extract_listing_data(self, item) -> Optional[Dict]:
        """
        Extract data from a single listing item
        
        Args:
            item: BeautifulSoup element containing listing
            
        Returns:
            Dictionary with property data or None if parsing fails
        """
        data = {}
        
        # Extract listing URL
        link_elem = item.find('a', href=True)
        if link_elem:
            href = link_elem['href']
            data['url'] = f"https://www.yad2.co.il{href}" if href.startswith('/') else href
        
        # Extract image URL
        img_elem = item.find('img', attrs={'data-testid': 'image'})
        if img_elem and img_elem.get('src'):
            data['image_url'] = img_elem['src']
        
        # Extract price
        price_elem = item.find(attrs={'data-testid': 'price'})
        if price_elem:
            data['price'] = self._clean_text(price_elem.get_text())
        
        # Extract street name and building number
        street_elem = item.find(attrs={'data-testid': 'street-name'})
        if street_elem:
            street_text = self._clean_text(street_elem.get_text())
            # Extract only letters for street name
            street_letters = re.sub(r'[^א-תa-zA-Z\s]', '', street_text).strip()
            # Extract only digits for building number
            building_digits = re.sub(r'[^\d]', '', street_text)
            
            if street_letters:
                data['street'] = street_letters
            if building_digits:
                data['building_number'] = building_digits
        
        # Extract property type, neighborhood, and city from first info line
        info_line_1 = item.find(attrs={'data-testid': 'item-info-line-1st'})
        if info_line_1:
            info_text = self._clean_text(info_line_1.get_text())
            # Split by comma
            parts = [p.strip() for p in info_text.split(',')]
            
            if len(parts) >= 1:
                data['property_type'] = parts[0]
            if len(parts) >= 2:
                # Second part might be neighborhood, could contain commas
                # If there are more than 3 parts, combine middle parts as neighborhood
                if len(parts) == 2:
                    data['city'] = parts[1]
                elif len(parts) == 3:
                    data['neighborhood'] = parts[1]
                    data['city'] = parts[2]
                else:
                    # More than 3 parts: first is type, last is city, rest is neighborhood
                    data['neighborhood'] = ', '.join(parts[1:-1])
                    data['city'] = parts[-1]
        
        # Extract rooms, floor, and size from second info line
        info_line_2 = item.find(attrs={'data-testid': 'item-info-line-2nd'})
        if info_line_2:
            info_text = self._clean_text(info_line_2.get_text())
            # Split by bullet point or similar separator
            parts = re.split(r'[•·]', info_text)
            parts = [p.strip() for p in parts if p.strip()]
            
            for part in parts:
                # Check for rooms (contains "חדרים" or "rooms")
                if 'חדר' in part or 'room' in part.lower():
                    # Extract number
                    room_match = re.search(r'\d+', part)
                    if room_match:
                        data['rooms'] = room_match.group()
                
                # Check for floor (contains "קומה" or "floor")
                elif 'קומה' in part or 'floor' in part.lower():
                    # Extract number
                    floor_match = re.search(r'\d+', part)
                    if floor_match:
                        data['floor'] = floor_match.group()
                
                # Check for size (contains "מ״ר" or "m²" or "sqm")
                elif 'מ״ר' in part or 'm²' in part or 'sqm' in part.lower():
                    # Extract number
                    size_match = re.search(r'\d+', part)
                    if size_match:
                        data['size_sqm'] = size_match.group()
        
        # Extract features/tags
        tags_box = item.find(attrs={'data-testid': 'item-tags-box'})
        if tags_box:
            tags = []
            for span in tags_box.find_all('span'):
                tag_text = self._clean_text(span.get_text())
                if tag_text:
                    tags.append(tag_text)
            if tags:
                data['features'] = tags
        
        # Only return if we got at least some data
        return data if len(data) > 0 else None
    
    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text by removing extra whitespace
        
        Args:
            text: Raw text string
            
        Returns:
            Cleaned text
        """
        return ' '.join(text.split()).strip()
    
    def get_next_page_url(self) -> Optional[str]:
        """
        Extract the URL for the next page of results
        
        Returns:
            URL string or None if no next page
        """
        # Look for pagination links in <ol class="list_list__wI8f9">
        pagination = self.soup.find('ol', class_=re.compile(r'list'))
        if not pagination:
            return None
        
        # Find all <li> items
        page_items = pagination.find_all('li')
        if not page_items:
            return None
        
        # Look for the "next" button or find the next page number
        for item in page_items:
            link = item.find('a')
            if link:
                # Check if this is a next button (aria-label or text)
                aria_label = link.get('aria-label', '').lower()
                if 'next' in aria_label or '›' in link.get_text() or '»' in link.get_text():
                    href = link.get('href')
                    if href:
                        if href.startswith('/'):
                            return f"https://www.yad2.co.il{href}"
                        return href
        
        return None
    
    def get_total_pages(self) -> Optional[int]:
        """
        Extract the total number of pages from pagination
        
        Returns:
            Total number of pages or None if not found
        """
        # Look for pagination in <ol class="list_list__wI8f9">
        pagination = self.soup.find('ol', class_=re.compile(r'list'))
        if not pagination:
            return None
        
        # Find all <li> items
        page_items = pagination.find_all('li')
        if not page_items:
            return None
        
        # The last meaningful <li> should contain the last page number
        # Iterate backwards to avoid "next" buttons
        for item in reversed(page_items):
            link = item.find('a')
            if link:
                text = link.get_text().strip()
                # Skip navigation buttons (next, previous)
                if text.isdigit():
                    return int(text)
        
        return None
