#!/usr/bin/env python3
"""Test HOMES scraper v2"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.scrapers.homes_scraper import HomesScraper

def test_homes_v2():
    scraper = HomesScraper()
    
    # Use v2 method
    scraper.scrape_area_v2("minato", max_pages=1)

if __name__ == "__main__":
    test_homes_v2()