"""
Duplicate detection module for identifying duplicate listings across sources.

Uses fuzzy title matching, price/area comparison to detect duplicates.
"""

import re
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime, timedelta
from difflib import SequenceMatcher


@dataclass
class DuplicateResult:
    """Result of duplicate detection."""
    is_duplicate: bool
    duplicate_of: Optional[int] = None
    similarity: float = 0.0
    keep_existing: bool = True


class DuplicateDetector:
    """Detects duplicate listings across sources."""
    
    def __init__(self, db_connection):
        """
        Initialize detector with database connection.
        
        Args:
            db_connection: Database connection for querying existing listings
        """
        self.db = db_connection
        self.similarity_threshold = 0.85
        self.price_tolerance = 0.05
        self.area_tolerance = 0.10
    
    def check_duplicate(self, new_listing: dict) -> DuplicateResult:
        """
        Check if listing is duplicate of existing listing.
        
        Args:
            new_listing: New listing to check
            
        Returns:
            DuplicateResult with duplicate status and original listing ID
        """
        # Get candidates from same city and district
        candidates = self._get_candidates(
            new_listing['city'],
            new_listing.get('district', ''),
            days=30,
            limit=100
        )
        
        # Normalize new listing title
        new_title_norm = self.normalize_title(new_listing['title'])
        
        for candidate in candidates:
            # Fuzzy title match
            candidate_title_norm = self.normalize_title(candidate['title'])
            title_similarity = self.fuzzy_match(new_title_norm, candidate_title_norm)
            
            if title_similarity < self.similarity_threshold:
                continue
            
            # Price match
            if not self._price_matches(candidate['price'], new_listing['price']):
                continue
            
            # Area match (if both have area)
            if candidate.get('area') and new_listing.get('area'):
                if not self._area_matches(candidate['area'], new_listing['area']):
                    continue
            
            # Found duplicate!
            return DuplicateResult(
                is_duplicate=True,
                duplicate_of=candidate['id'],
                similarity=title_similarity,
                keep_existing=candidate['created_at'] < new_listing.get('created_at', datetime.now().isoformat())
            )
        
        return DuplicateResult(is_duplicate=False)
    
    def normalize_title(self, title: str) -> str:
        """
        Normalize title for comparison.
        
        Args:
            title: Raw title
            
        Returns:
            Normalized title
        """
        # Lowercase
        title = title.lower()
        
        # Remove special characters
        title = re.sub(r'[^\w\s]', '', title)
        
        # Remove numbers
        title = re.sub(r'\d+', '', title)
        
        # Remove common prefixes
        prefixes = [
            'wynajmę', 'wynajem', 'mieszkanie', 'kawalerka',
            'do wynajęcia', 'pokój', 'dom', 'studio', 'apartament'
        ]
        for prefix in prefixes:
            title = title.replace(prefix, '')
        
        # Remove extra whitespace
        title = ' '.join(title.split())
        
        return title.strip()
    
    def fuzzy_match(self, text1: str, text2: str) -> float:
        """
        Calculate fuzzy similarity score (0-1).
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity ratio between 0 and 1
        """
        return SequenceMatcher(None, text1, text2).ratio()
    
    def _price_matches(self, price1: int, price2: int) -> bool:
        """Check if prices match within tolerance."""
        if price1 == 0 or price2 == 0:
            return False
        
        diff_pct = abs(price1 - price2) / max(price1, price2)
        return diff_pct <= self.price_tolerance
    
    def _area_matches(self, area1: float, area2: float) -> bool:
        """Check if areas match within tolerance."""
        if area1 == 0 or area2 == 0:
            return True  # Skip if either missing
        
        diff_pct = abs(area1 - area2) / max(area1, area2)
        return diff_pct <= self.area_tolerance
    
    def _get_candidates(self, city: str, district: str, days: int = 30, limit: int = 100) -> List[dict]:
        """
        Get candidate listings for duplicate checking.
        
        Args:
            city: City name
            district: District name
            days: Number of days to look back
            limit: Maximum number of candidates
            
        Returns:
            List of candidate listings
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        query = """
            SELECT id, title, price, area, created_at
            FROM apartments
            WHERE city = ?
            AND district = ?
            AND created_at > ?
            AND duplicate_of IS NULL
            ORDER BY created_at DESC
            LIMIT ?
        """
        
        cursor = self.db.execute(query, (city, district, cutoff_date, limit))
        columns = [desc[0] for desc in cursor.description]
        
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def merge_listings(self, original_id: int, duplicate_id: int) -> None:
        """
        Merge duplicate listing data into original.
        
        Args:
            original_id: ID of original listing to keep
            duplicate_id: ID of duplicate listing to mark
        """
        # Mark duplicate
        self.db.execute(
            "UPDATE apartments SET duplicate_of = ? WHERE id = ?",
            (original_id, duplicate_id)
        )
        self.db.commit()
