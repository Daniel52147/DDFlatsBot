"""
Geographic validation module for ensuring listings are correctly assigned to cities.

This module provides coordinate-based, postal code, and district validation
to eliminate cross-city contamination in search results.
"""

import re
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple


# City boundary coordinates (lat_min, lat_max, lon_min, lon_max)
CITY_BOUNDARIES = {
    'Warszawa': (52.0975, 52.3690, 20.8517, 21.2711),
    'Kraków': (49.9700, 50.1280, 19.8094, 20.2158),
    'Wrocław': (51.0509, 51.1919, 16.8799, 17.1428),
    'Gdańsk': (54.2797, 54.4358, 18.4647, 18.7858),
    'Poznań': (52.3396, 52.4897, 16.8094, 17.0428),
    'Łódź': (51.6800, 51.8400, 19.3500, 19.5800),
    'Katowice': (50.2000, 50.3200, 18.9000, 19.1200),
    'Lublin': (51.1800, 51.3200, 22.4000, 22.6500),
    'Szczecin': (53.3800, 53.5000, 14.4500, 14.6500),
    'Białystok': (53.0800, 53.1800, 23.0000, 23.2500),
}

# Postal code ranges for each city (start, end)
CITY_POSTAL_RANGES = {
    'Warszawa': [('00', '05')],
    'Kraków': [('30', '32')],
    'Wrocław': [('50', '54')],
    'Gdańsk': [('80', '80')],
    'Poznań': [('60', '62')],
    'Łódź': [('90', '94')],
    'Katowice': [('40', '44')],
    'Lublin': [('20', '21')],
    'Szczecin': [('70', '71')],
    'Białystok': [('15', '16')],
}

# False-positive street names that exist in multiple cities
def _normalize_street(s: str) -> str:
    """ASCII-friendly normalize for street name matching."""
    repl = str.maketrans("ąćęłńóśźż", "acelnoszz")
    return s.lower().translate(repl)


FALSE_POSITIVE_STREETS = {
    'Warszawa': ['wroclawska', 'krakowska', 'poznanska', 'gdanska'],
    'Kraków': ['warszawska', 'wroclawska', 'poznanska', 'gdanska'],
    'Wrocław': ['warszawska', 'krakowska', 'poznanska', 'gdanska'],
    'Gdańsk': ['warszawska', 'krakowska', 'wroclawska', 'poznanska'],
    'Poznań': ['warszawska', 'krakowska', 'wroclawska', 'gdanska'],
    'Łódź': ['warszawska', 'krakowska', 'wroclawska', 'gdanska', 'poznanska'],
    'Katowice': ['warszawska', 'krakowska', 'wroclawska', 'gdanska', 'poznanska'],
    'Lublin': ['warszawska', 'krakowska', 'wroclawska', 'gdanska', 'poznanska'],
    'Szczecin': ['warszawska', 'krakowska', 'wroclawska', 'poznanska'],
    'Białystok': ['warszawska', 'krakowska', 'wroclawska', 'gdanska', 'poznanska'],
}


@dataclass
class ValidationResult:
    """Result of geographic validation."""
    valid: bool
    city: Optional[str] = None
    district: Optional[str] = None
    confidence: int = 0
    reason: Optional[str] = None


class GeographicValidator:
    """Validates listing geographic data against city boundaries."""
    
    def __init__(self, city_districts: Dict[str, List[str]]):
        """
        Initialize validator with city district mappings.
        
        Args:
            city_districts: Dictionary mapping city names to lists of valid districts
        """
        self.city_districts = city_districts
    
    def validate(self, listing: dict, target_city: str) -> ValidationResult:
        """
        Validate listing belongs to target city.
        
        Args:
            listing: Raw listing data with title, address, district, coordinates
            target_city: Expected city name
            
        Returns:
            ValidationResult with valid flag, confidence score, and reason
        """
        confidence = 0
        validated_district = None
        
        # Priority 1: Coordinate validation (highest confidence)
        if listing.get('lat') and listing.get('lon'):
            if self.is_within_city_bounds(listing['lat'], listing['lon'], target_city):
                confidence += 50
                # Try to find district by coordinates
                validated_district = listing.get('district')
            else:
                return ValidationResult(
                    valid=False,
                    reason="coordinates_outside_city"
                )
        
        # Priority 2: Postal code validation
        text = f"{listing.get('title', '')} {listing.get('address', '')}"
        postal = self.extract_postal_code(text)
        if postal:
            if self.is_postal_in_city(postal, target_city):
                confidence += 30
            else:
                return ValidationResult(
                    valid=False,
                    reason="postal_code_mismatch"
                )
        
        # Trust listings scraped from a city-specific feed when no contradictory geo data
        if listing.get('source_city') == target_city:
            confidence = max(confidence, 50)

        # Priority 3: District validation
        district = listing.get('district', '')
        if district:
            normalized_district = self.normalize_district(district, target_city)
            if normalized_district:
                confidence += 20
                validated_district = normalized_district
            elif self.is_false_positive_street(district, target_city):
                # Street named after another city but inside target_city — keep district text, no penalty
                validated_district = district
                confidence += 10
        
        # Require minimum confidence
        if confidence >= 50:
            return ValidationResult(
                valid=True,
                city=target_city,
                district=validated_district or district or target_city,
                confidence=confidence,
                reason=None
            )
        else:
            return ValidationResult(
                valid=False,
                reason="insufficient_confidence"
            )
    
    def extract_postal_code(self, text: str) -> Optional[str]:
        """
        Extract Polish postal code (XX-XXX format) from text.
        
        Args:
            text: Text to search for postal code
            
        Returns:
            Postal code if found, None otherwise
        """
        match = re.search(r'\b(\d{2})-\d{3}\b', text)
        return match.group(1) if match else None
    
    def is_postal_in_city(self, postal_prefix: str, city: str) -> bool:
        """
        Check if postal code prefix belongs to city.
        
        Args:
            postal_prefix: Two-digit postal code prefix
            city: City name
            
        Returns:
            True if postal code belongs to city
        """
        if city not in CITY_POSTAL_RANGES:
            return False
        
        ranges = CITY_POSTAL_RANGES[city]
        for start, end in ranges:
            if start <= postal_prefix <= end:
                return True
        return False
    
    def is_within_city_bounds(self, lat: float, lon: float, city: str) -> bool:
        """
        Check if coordinates fall within city boundaries.
        
        Args:
            lat: Latitude
            lon: Longitude
            city: City name
            
        Returns:
            True if coordinates are within city bounds
        """
        if city not in CITY_BOUNDARIES:
            return False
        
        lat_min, lat_max, lon_min, lon_max = CITY_BOUNDARIES[city]
        return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
    
    def normalize_district(self, district: str, city: str) -> Optional[str]:
        """
        Normalize district name to canonical form.
        
        Args:
            district: Raw district name
            city: City name
            
        Returns:
            Normalized district name if valid, None otherwise
        """
        if city not in self.city_districts:
            return None
        
        # Normalize: lowercase, remove extra spaces
        normalized = ' '.join(district.lower().strip().split())
        
        # Check against canonical district list
        city_districts_lower = [d.lower() for d in self.city_districts[city]]
        
        if normalized in city_districts_lower:
            # Return original case from canonical list
            idx = city_districts_lower.index(normalized)
            return self.city_districts[city][idx]
        
        return None
    
    def is_false_positive_street(self, street_name: str, city: str) -> bool:
        """
        Check if street name is a known false positive for this city.
        
        Args:
            street_name: Street name to check
            city: City name
            
        Returns:
            True if this is a false positive street name
        """
        if city not in FALSE_POSITIVE_STREETS:
            return False
        
        normalized = _normalize_street(street_name)
        return any(fp in normalized for fp in FALSE_POSITIVE_STREETS[city])
