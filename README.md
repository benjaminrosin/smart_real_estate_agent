# Yad2 Real Estate Scraper

A Python web scraper for collecting rental property listings from yad2.co.il.

## Features

- Scrapes rental property listings from Yad2.co.il
- Extracts property details (price, address, rooms, etc.)
- Rate limiting and retry logic for robust scraping
- Saves data Mongo DB
- Configurable page limits

## Usage

### using Docker:
```bash
docker compose up -d --build
```

### Locally:
#### Install:
1. Activate the virtual environment:
```bash
venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

#### Run:

Basic usage (scrape all pages):
```bash
python main.py
```

Custom options:
```bash
# Scrape 10 pages
python main.py --pages 10
```

## Project Structure

```
project/
├── scraper/
│   ├── config.py        # Configuration settings
│   ├── scraper.py       # Main scraper logic
│   ├── parser.py        # HTML parsing
│   └── db_manager.py    # Data base manager
├── main.py              # CLI entry point
├── requirements.txt     # Dependencies
├── .env                 # Environment variables
├── Dockerfile           # Docker file to run the scraper
└── Docker-compose.yml   # Docker orchestration
```

## Configuration

Edit `scraper/config.py` to adjust:
- Request delay between pages
- Maximum retries
- Default output directory
- User agent and headers

## Notes

- The scraper respects rate limits with 30-second delays between requests
- The parser may need adjustments based on Yad2's HTML structure
