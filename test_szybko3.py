import requests, sys

r = requests.get(
    'https://www.szybko.pl/nieruchomosci/wynajem/mieszkania/warszawa',
    timeout=15,
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
)
print("Status:", r.status_code, file=sys.stderr)
print("Size:", len(r.text), file=sys.stderr)
sys.stderr.flush()

with open('szybko_dump.html', 'w', encoding='utf-8', errors='replace') as f:
    f.write(r.text)

print("DONE", file=sys.stderr)
sys.stderr.flush()
sys.exit(0)
