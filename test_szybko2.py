import requests

r = requests.get(
    'https://www.szybko.pl/nieruchomosci/wynajem/mieszkania/warszawa',
    timeout=15,
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
)
with open('szybko_dump.html', 'w', encoding='utf-8') as f:
    f.write(r.text)
print("Saved", len(r.text), "bytes")
