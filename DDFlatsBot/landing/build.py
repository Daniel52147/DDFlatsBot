
# Build script for DDFlatsBot landing page
html = open("index.html", encoding="utf-8").read()
print(f"Current size: {len(html)} chars, {html.count(chr(10))} lines")
print("Has nav:", "<nav>" in html)
print("Has hero:", "class=\"hero\"" in html)
print("Has footer:", "<footer>" in html)
