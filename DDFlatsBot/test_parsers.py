#!/usr/bin/env python3
"""Test parsers for all cities."""
import sys
sys.path.insert(0, '.')

from parser.parser_olx import parse_olx
from parser.parser_otodom import parse_otodom
from config import CITIES

def test_city(city: str):
    print(f"\n{'='*60}")
    print(f"Testing {city}")
    print('='*60)
    
    # Test OLX
    print(f"\n[OLX/{city}]")
    try:
        results = parse_olx(city)
        print(f"✅ Found {len(results)} listings")
        if results:
            print(f"Sample: {results[0]['title'][:50]}... - {results[0]['price']} zł")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test Otodom
    print(f"\n[Otodom/{city}]")
    try:
        results = parse_otodom(city)
        print(f"✅ Found {len(results)} listings")
        if results:
            print(f"Sample: {results[0]['title'][:50]}... - {results[0]['price']} zł")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    for city in CITIES.keys():
        test_city(city)
    
    print(f"\n{'='*60}")
    print("Testing complete!")
    print('='*60)
