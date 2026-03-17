"""
Run from DDFlatsBot folder:
  python test_parsers.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from parser.parser_olx import parse_olx
from parser.parser_otodom import parse_otodom
from parser.parser_gratka import parse_gratka
from parser.parser_morizon import parse_morizon


def test(name, fn):
    print(f"\n{'='*40}")
    print(f"Testing {name}...")
    try:
        results = fn()
        print(f"✅ {name}: {len(results)} listings")
        if results:
            r = results[0]
            print(f"   Title:    {r.get('title','?')[:60]}")
            print(f"   Price:    {r.get('price','?')} zł")
            print(f"   District: {r.get('district','?')}")
            print(f"   Rooms:    {r.get('rooms','?')}")
            print(f"   Link:     {r.get('link','?')[:70]}")
        else:
            print(f"   ⚠️  No results — site may be blocking")
    except Exception as e:
        print(f"❌ {name} FAILED: {e}")


test("OLX",    parse_olx)
test("Otodom", parse_otodom)
test("Gratka", parse_gratka)
test("Morizon",parse_morizon)

print("\n" + "="*40)
print("Done.")
