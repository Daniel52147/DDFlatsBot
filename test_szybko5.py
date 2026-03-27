import urllib.request, sys

req = urllib.request.Request(
    'https://www.szybko.pl/nieruchomosci/wynajem/mieszkania/warszawa',
    headers={'User-Agent': 'Mozilla/5.0', 'Connection': 'close'}
)
with urllib.request.urlopen(req, timeout=10) as resp:
    raw = resp.read(200000)  # max 200KB

html = raw.decode('utf-8', errors='replace')
print("Size:", len(html))
print("has ld+json:", 'ld+json' in html)
print("has article:", '<article' in html)
print("has ogloszenie:", 'ogloszenie' in html)
print("has NEXT_DATA:", '__NEXT_DATA__' in html)
print("has mediaproxy:", 'mediaproxy' in html)

idx = html.find('ogloszenie')
if idx > 0:
    print("Sample:", html[max(0,idx-30):idx+100])
