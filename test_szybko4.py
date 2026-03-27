import requests, sys

r = requests.get(
    'https://www.szybko.pl/nieruchomosci/wynajem/mieszkania/warszawa',
    timeout=10,
    headers={'User-Agent': 'Mozilla/5.0'},
    stream=False
)
print(r.status_code, len(r.content))
html = r.content.decode('utf-8', errors='replace')
print("Decoded:", len(html))

# Quick checks without heavy regex
print("has ld+json:", 'ld+json' in html)
print("has article:", '<article' in html)
print("has szybko link:", 'szybko.pl/ogloszenie' in html or 'szybko.pl/nieruchomosci/' in html)
print("has NEXT_DATA:", '__NEXT_DATA__' in html)
print("has mediaproxy:", 'mediaproxy' in html)

# Find first listing link manually
idx = html.find('szybko.pl/ogloszenie')
if idx > 0:
    print("Link sample:", html[idx-10:idx+80])
