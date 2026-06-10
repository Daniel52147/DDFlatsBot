"""
Integration module for validators in parser pipeline.

Provides helper functions to integrate geographic validation and duplicate detection
into the parser workflow.
"""

from typing import Optional, Dict
from .geographic import GeographicValidator, ValidationResult
from .duplicates import DuplicateDetector, DuplicateResult
from config import CITY_DISTRICTS


class ValidationPipeline:
    """Pipeline for validating and processing parsed listings."""
    
    def __init__(self, db_connection):
        """
        Initialize validation pipeline.
        
        Args:
            db_connection: Database connection
        """
        self.geo_validator = GeographicValidator(CITY_DISTRICTS)
        self.dup_detector = DuplicateDetector(db_connection)
        self.db = db_connection
    
    def process_listing(self, listing: dict, target_city: str) -> Optional[dict]:
        """
        Process listing through validation pipeline.
        
        Args:
            listing: Raw listing data
            target_city: Expected city for this listing
            
        Returns:
            Processed listing dict if valid, None if rejected
        """
        # Step 1: Geographic validation
        geo_result = self.geo_validator.validate(listing, target_city)
        
        if not geo_result.valid:
            reason = geo_result.reason or "unknown"
            link = listing.get("link", "") or ""
            try:
                from database.db import log_validation_reject
                log_validation_reject(reason, target_city, link)
            except Exception:
                pass
            if reason == "link_city_mismatch":
                from validation.geographic import city_from_link
                detected = city_from_link(link)
                print(
                    f"[Validation] link_city_mismatch: target={target_city} "
                    f"detected={detected} link={link[:120]}"
                )
            else:
                print(f"[Validation] Rejected listing: {reason}")
            return None
        
        listing["city"] = geo_result.city or target_city
        listing["source_city"] = listing["city"]
        if geo_result.district:
            listing["district"] = geo_result.district
        
        # Step 2: Duplicate detection
        dup_result = self.dup_detector.check_duplicate(listing)
        
        if dup_result.is_duplicate:
            print(f"[Validation] Duplicate skipped: {listing['title'][:50]}... -> {dup_result.duplicate_of}")
            return None

        return listing
    
    def save_listing(self, listing: dict) -> Optional[int]:
        """
        Save validated listing to database.
        
        Args:
            listing: Validated listing data
            
        Returns:
            Listing ID if saved, None if error
        """
        if listing.get("duplicate_of"):
            return None
        try:
            # Check if listing already exists (by link)
            existing = self.db.execute(
                "SELECT id FROM apartments WHERE link = ?",
                (listing['link'],)
            ).fetchone()
            
            if existing:
                # Update existing listing
                self._update_listing(existing[0], listing)
                return existing[0]
            else:
                # Insert new listing
                return self._insert_listing(listing)
        
        except Exception as e:
            print(f"[Validation] Error saving listing: {e}")
            return None
    
    def _insert_listing(self, listing: dict) -> int:
        """Insert new listing into database."""
        cursor = self.db.execute("""
            INSERT INTO apartments (
                title, price, district, city, rooms, area, floor, furnished,
                link, image, source, created_at,
                lat, lon, postal_code, source_city, duplicate_of, quality_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            listing['title'],
            listing['price'],
            listing['district'],
            listing['city'],
            listing.get('rooms'),
            listing.get('area'),
            listing.get('floor'),
            listing.get('furnished', -1),
            listing['link'],
            listing.get('image'),
            listing['source'],
            listing.get('created_at'),
            listing.get('lat'),
            listing.get('lon'),
            listing.get('postal_code'),
            listing.get('source_city'),
            listing.get('duplicate_of'),
            listing.get('quality_score', 50),
        ))
        
        self.db.commit()
        return cursor.lastrowid
    
    def _update_listing(self, listing_id: int, listing: dict) -> None:
        """Update existing listing in database."""
        self.db.execute("""
            UPDATE apartments SET
                title = ?, price = ?, district = ?, city = ?,
                rooms = ?, area = ?, floor = ?, furnished = ?,
                image = ?, lat = ?, lon = ?, postal_code = ?,
                source_city = ?, duplicate_of = ?, quality_score = ?
            WHERE id = ?
        """, (
            listing['title'],
            listing['price'],
            listing['district'],
            listing['city'],
            listing.get('rooms'),
            listing.get('area'),
            listing.get('floor'),
            listing.get('furnished', -1),
            listing.get('image'),
            listing.get('lat'),
            listing.get('lon'),
            listing.get('postal_code'),
            listing.get('source_city'),
            listing.get('duplicate_of'),
            listing.get('quality_score', 50),
            listing_id,
        ))
        
        self.db.commit()


def create_validation_pipeline(db_connection) -> ValidationPipeline:
    """
    Factory function to create validation pipeline.
    
    Args:
        db_connection: Database connection
        
    Returns:
        Configured ValidationPipeline instance
    """
    return ValidationPipeline(db_connection)
