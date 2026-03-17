import requests
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime

conn = sqlite3.connect("Flats.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS apartments(
id INTEGER PRIMARY KEY AUTOINCREMENT,
title TEXT,
price INTEGER,
district TEXT,
link TEXT UNIQUE,
source TEXT,
date TEXT
)
""")

conn.commit()


def save_apartment(title, price, district, link, source):

    cursor.execute("SELECT id FROM apartments WHERE link=?", (link,))
    if cursor.fetchone():
        return

    cursor.execute("""
    INSERT INTO apartments(title,price,district,link,source,date)
    VALUES(?,?,?,?,?,?)
    """, (title, price, district, link, source, datetime.now()))

    conn.commit()


# OLX
def parse_olx():

    url = "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/"
    r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"})

    soup = BeautifulSoup(r.text,"html.parser")

    offers = soup.find_all("a")

    for offer in offers:

        title = offer.text.strip()

        if "zł" not in title:
            continue

        price = 0

        link = offer.get("href")

        save_apartment(title,price,"Warsaw",link,"OLX")

    print("OLX parsed")


# Gumtree
def parse_gumtree():

    url = "https://www.gumtree.pl/s-mieszkania-i-domy-do-wynajecia/warszawa/"
    r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"})

    soup = BeautifulSoup(r.text,"html.parser")

    offers = soup.find_all("a")

    for offer in offers:

        title = offer.text.strip()

        if "zł" not in title:
            continue

        link = "https://www.gumtree.pl" + offer.get("href")

        save_apartment(title,0,"Warsaw",link,"Gumtree")

    print("Gumtree parsed")


# Otodom
def parse_otodom():

    url = "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa"
    r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"})

    soup = BeautifulSoup(r.text,"html.parser")

    offers = soup.find_all("a")

    for offer in offers:

        title = offer.text.strip()

        if "zł" not in title:
            continue

        link = offer.get("href")

        save_apartment(title,0,"Warsaw",link,"Otodom")

    print("Otodom parsed")


if __name__ == "__main__":

    parse_olx()
    parse_gumtree()
    parse_otodom()