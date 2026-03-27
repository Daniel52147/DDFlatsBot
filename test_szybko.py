import requests, re, json

r = requests.get(
    'https://www.szybko.pl/nieruchomosci/wynajem/mieszkania/warszawa',
    timeout=15,
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
)
html = r.text
print("Status:", r.status_code, "Size:", len(html))
print("JSON-LD blocks:", len(re.findall(r'application/ld\+json', html)))
print("Articles:", len(re.findall(r'<article', html)))
links = re.findall(r'href="(https://www\.szybko\.pl/[^"]{20,})"', html)
print("Links:", len(links))
if links:
    print("Sample link:", links[0])
imgs = re.findall(r'src="(https://mediaproxy[^"]+)"', html)
print("Images:", len(imgs))
if imgs:
    print("Sample img:", imgs[0])

# Check for __NEXT_DATA__ or similar
if '__NEXT_DATA__' in html:
    print("Has __NEXT_DATA__")
if 'window.__' in html:
    matches = re.findall(r'window\.__(\w+)', html)
    print("window vars:", matches[:5])
