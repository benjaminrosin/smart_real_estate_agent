# Yad2 Real Estate Scraper

A Python web scraper for collecting rental property listings from yad2.co.il.

## Features

- Scrapes rental property listings from Yad2.co.il
- Extracts property details (price, address, rooms, etc.)
- Rate limiting and retry logic for robust scraping
- Saves data to CSV and/or JSON formats
- Configurable page limits

## Installation

1. Activate the virtual environment:
```bash
venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Basic usage (scrape 5 pages, save to both CSV and JSON):
```bash
python main.py
```

Custom options:
```bash
# Scrape 10 pages
python main.py --pages 10

# Save only as CSV
python main.py --output csv

# Save only as JSON
python main.py --output json

# Custom filename
python main.py --filename my_listings
```

## Project Structure

```
project/
├── scraper/
│   ├── __init__.py      # Package initialization
│   ├── config.py        # Configuration settings
│   ├── scraper.py       # Main scraper logic
│   ├── parser.py        # HTML parsing
│   └── storage.py       # Data storage
├── data/                # Output directory (created automatically)
├── main.py              # CLI entry point
└── requirements.txt     # Dependencies
```

## Configuration

Edit `scraper/config.py` to adjust:
- Request delay between pages
- Maximum retries
- Default output directory
- User agent and headers

## Notes

- The scraper respects rate limits with 2-second delays between requests
- Output files are timestamped automatically
- The parser may need adjustments based on Yad2's HTML structure
