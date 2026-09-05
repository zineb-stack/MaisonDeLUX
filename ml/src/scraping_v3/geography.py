"""Conservative Morocco city/region reference and location validation."""
from __future__ import annotations

import re
from typing import Any

from .schema import clean_text, normalized


REGION_CITIES: dict[str, tuple[str, ...]] = {
    "Tanger-Tétouan-Al Hoceïma": (
        "Tanger", "Tétouan", "Al Hoceïma", "Larache", "Chefchaouen", "Asilah",
        "Ksar El Kébir", "Fnideq", "M'diq", "Ouezzane",
    ),
    "L'Oriental": ("Oujda", "Nador", "Berkane", "Jerada", "Taourirt", "Guercif", "Saïdia", "Driouch"),
    "Fès-Meknès": ("Fès", "Meknès", "Ifrane", "Taza", "Sefrou", "El Hajeb", "Azrou", "Boulemane"),
    "Rabat-Salé-Kénitra": ("Rabat", "Salé", "Kénitra", "Témara", "Skhirat", "Khémisset", "Sidi Kacem", "Sidi Slimane"),
    "Béni Mellal-Khénifra": ("Béni Mellal", "Khénifra", "Khouribga", "Azilal", "Fquih Ben Salah"),
    "Casablanca-Settat": (
        "Casablanca", "Settat", "El Jadida", "Mohammedia", "Berrechid", "Benslimane",
        "Azemmour", "Sidi Bennour", "Bouskoura", "Dar Bouazza", "Médiouna", "Nouaceur",
    ),
    "Marrakech-Safi": ("Marrakech", "Safi", "Essaouira", "El Kelâa des Sraghna", "Youssoufia", "Chichaoua", "Ben Guerir"),
    "Drâa-Tafilalet": ("Errachidia", "Ouarzazate", "Midelt", "Tinghir", "Zagora", "Rissani"),
    "Souss-Massa": ("Agadir", "Inezgane", "Aït Melloul", "Taroudant", "Tiznit", "Tata", "Taghazout"),
    "Guelmim-Oued Noun": ("Guelmim", "Tan-Tan", "Sidi Ifni", "Assa"),
    "Laâyoune-Sakia El Hamra": ("Laâyoune", "Boujdour", "Tarfaya", "Es-Semara"),
    "Dakhla-Oued Ed-Dahab": ("Dakhla", "Aousserd"),
}

ALIASES: dict[str, str] = {}
CITY_TO_REGION: dict[str, str] = {}
for _region, _cities in REGION_CITIES.items():
    for _city in _cities:
        ALIASES[normalized(_city)] = _city
        CITY_TO_REGION[normalized(_city)] = _region
ALIASES.update({
    "casa": "Casablanca", "dar el beida": "Casablanca", "fez": "Fès",
    "meknes": "Meknès", "kenitra": "Kénitra", "sale": "Salé", "temara": "Témara",
    "tetouan": "Tétouan", "tangier": "Tanger", "marrakesh": "Marrakech",
    "beni mellal": "Béni Mellal", "laayoune": "Laâyoune", "al hoceima": "Al Hoceïma",
    "ait melloul": "Aït Melloul", "essaouira": "Essaouira",
    "الدار البيضاء": "Casablanca", "الرباط": "Rabat", "مراكش": "Marrakech",
    "طنجة": "Tanger", "اكادير": "Agadir", "أكادير": "Agadir", "فاس": "Fès",
    "مكناس": "Meknès", "وجدة": "Oujda", "القنيطرة": "Kénitra", "تطوان": "Tétouan",
    "الصويرة": "Essaouira", "الجديدة": "El Jadida", "اسفي": "Safi", "آسفي": "Safi",
    "العيون": "Laâyoune", "الداخلة": "Dakhla",
})

PROMOTIONAL_OR_SENTENCE = re.compile(
    r"\b(a quelques minutes|dans un quartier|le quartier de|l un des secteurs|proche de|a proximite|proximite de|"
    r"magnifique|ideal(?:e)?|opportunite|profitez|decouvrez|offre|situe(?:e)?|beautiful|located|"
    r"dispose|compose|beneficie|vous propose|a vendre|a louer|vente|location|prix|"
    r"على بعد دقائق|في حي|للبيع|للايجار)\b"
)
GENERIC_LOCATION = {
    "maroc", "centre ville", "quartier", "adresse", "emplacement", "non precise",
    "autre secteur", "appartement", "maison", "villa", "immobilier",
}


def canonical_city(value: Any) -> str | None:
    value = clean_text(value)
    if not value:
        return None
    key = normalized(value)
    if key in ALIASES:
        return ALIASES[key]
    # Match an explicitly named city inside a structured location string.
    matches = [(len(alias), city) for alias, city in ALIASES.items() if re.search(rf"(?:^|\s){re.escape(alias)}(?:$|\s)", key)]
    return max(matches)[1] if matches else None


def region_for_city(city: Any) -> str | None:
    city = canonical_city(city)
    return CITY_TO_REGION.get(normalized(city)) if city else None


def valid_neighborhood(value: Any, city: Any = None) -> bool:
    text = clean_text(value)
    key = normalized(text)
    if not text or key in GENERIC_LOCATION or len(text) > 55:
        return False
    tokens = key.split()
    if not 1 <= len(tokens) <= 7 or PROMOTIONAL_OR_SENTENCE.search(key):
        return False
    if re.search(r"[.!?;:]|\b\d+\s*m(?:2|²)\b", text.casefold()):
        return False
    if re.search(r"\b(?:de|du|des|a|dans|avec|sur)$", key):
        return False
    city_key = normalized(canonical_city(city))
    return not city_key or key != city_key


def parse_location(city_value: Any, neighborhood_value: Any, location_raw: Any) -> tuple[str | None, str | None, str | None]:
    city = canonical_city(city_value)
    raw = clean_text(location_raw)
    if not city and raw:
        city = canonical_city(raw)
    neighborhood = clean_text(neighborhood_value)
    if neighborhood and not valid_neighborhood(neighborhood, city):
        neighborhood = None
    if not neighborhood and raw and city:
        parts = [part.strip() for part in re.split(r"[,|>]", raw) if part.strip()]
        for part in parts:
            if canonical_city(part) == city:
                continue
            if valid_neighborhood(part, city):
                neighborhood = part
                break
    return city, neighborhood, region_for_city(city)
