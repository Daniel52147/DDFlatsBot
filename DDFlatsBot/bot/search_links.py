"""Per-city URLs on OLX, Otodom, Gratka, Morizon — fallback when DB is empty."""
from config import city_slug


def city_platform_urls(city: str) -> dict[str, str]:
    slug = city_slug(city)
    return {
        "olx": f"https://www.olx.pl/nieruchomosci/mieszkania/wynajem/{slug}/",
        "otodom": f"https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/{slug}",
        "gratka": f"https://gratka.pl/nieruchomosci/mieszkania/{slug}/wynajem",
        "morizon": f"https://www.morizon.pl/do-wynajecia/mieszkania/{slug}/",
        "adresowo": f"https://adresowo.pl/mieszkania/wynajem/{slug}",
    }
