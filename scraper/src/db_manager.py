"""
MongoDB Atlas Database Manager for Yad2 Scraper
Handles connection and CRUD operations for rental listings
"""
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError
from typing import List, Dict, Optional, Any
from datetime import datetime
import os


class MongoDBManager:
    """Manager class for MongoDB Atlas operations"""
    
    def __init__(self, connection_string: Optional[str] = None, database_name: str = "yad2_scraper"):
        """
        Initialize MongoDB connection
        
        Args:
            connection_string: MongoDB Atlas connection string
                              If None, will look for MONGO_URI environment variable
            database_name: Name of the database to use
        """
        self.connection_string = connection_string or os.getenv('MONGO_URI')
        if not self.connection_string:
            raise ValueError("MongoDB connection string not provided. Set MONGO_URI environment variable or pass connection_string parameter.")
        
        self.database_name = database_name
        self.client = None
        self.db = None
        self.collection = None
        self._connected = False
        
    def connect(self, collection_name: str = "listings") -> bool:
        """
        Establish connection to MongoDB Atlas
        
        Args:
            collection_name: Name of the collection to use
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client = MongoClient(self.connection_string)
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client[self.database_name]
            self.collection = self.db[collection_name]
            self._connected = True
            print(f"✓ Connected to MongoDB Atlas - Database: {self.database_name}, Collection: {collection_name}")
            return True
        except ConnectionFailure as e:
            print(f"✗ Failed to connect to MongoDB: {e}")
            self._connected = False
            return False
        except Exception as e:
            print(f"✗ Unexpected error during connection: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        """Close MongoDB connection"""
        if self.client is not None:
            self.client.close()
            self._connected = False
            print("✓ Disconnected from MongoDB")
    
    # CREATE operations
    
    def insert_listing(self, listing: Dict[str, Any]) -> Optional[str]:
        """
        Insert a single listing into the database
        
        Args:
            listing: Dictionary containing listing data
            
        Returns:
            Inserted document ID as string, or None if failed
        """
        if not self._connected:
            print("✗ Not connected to database")
            return None
        
        try:
            # Add timestamp
            listing['scraped_at'] = datetime.utcnow()
            result = self.collection.insert_one(listing)
            return str(result.inserted_id)
        except DuplicateKeyError:
            print(f"✗ Listing already exists (duplicate key)")
            return None
        except Exception as e:
            print(f"✗ Error inserting listing: {e}")
            return None
    
    def insert_listings(self, listings: List[Dict[str, Any]]) -> int:
        """
        Insert multiple listings into the database (DEPRECATED - use upsert_listings)
        
        Args:
            listings: List of listing dictionaries
            
        Returns:
            Number of successfully inserted documents
        """
        if not self._connected:
            print("✗ Not connected to database")
            return 0
        
        if not listings:
            print("✗ No listings to insert")
            return 0
        
        try:
            # Add timestamp to all listings
            for listing in listings:
                listing['scraped_at'] = datetime.utcnow()
            
            result = self.collection.insert_many(listings, ordered=False)
            inserted_count = len(result.inserted_ids)
            print(f"✓ Inserted {inserted_count} listings")
            return inserted_count
        except Exception as e:
            print(f"✗ Error inserting listings: {e}")
            return 0
    
    def upsert_listings(self, listings: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Upsert multiple listings using URL as _id
        Updates existing listings and merges features array
        
        Args:
            listings: List of listing dictionaries (must contain 'url' field)
            
        Returns:
            Dictionary with counts: {'inserted': X, 'updated': Y, 'errors': Z}
        """
        if not self._connected:
            print("✗ Not connected to database")
            return {'inserted': 0, 'updated': 0, 'errors': 0}
        
        if not listings:
            print("✗ No listings to upsert")
            return {'inserted': 0, 'updated': 0, 'errors': 0}
        
        inserted_count = 0
        updated_count = 0
        error_count = 0
        
        current_time = datetime.utcnow()
        
        for listing in listings:
            try:
                url = listing.get('url')
                oid = url.split('/')[-1] if url else None
                if not url or not oid:
                    error_count += 1
                    continue
                
                # Check if listing exists
                existing = self.collection.find_one({'_id': oid})
                
                if existing:
                    # Update existing listing
                    update_doc = listing.copy()
                    update_doc['last_seen'] = current_time
                    update_doc['updated_at'] = current_time
                    update_doc['deleted'] = False
                    
                    # Merge features if both exist
                    if 'features' in update_doc and 'features' in existing:
                        # Combine and deduplicate features
                        existing_features = set(existing.get('features', []))
                        new_features = set(update_doc.get('features', []))
                        merged_features = list(existing_features.union(new_features))
                        update_doc['features'] = merged_features
                    
                    # Remove _id from update doc to avoid modifying it
                    update_doc.pop('_id', None)
                    
                    self.collection.update_one(
                        {'_id': oid},
                        {'$set': update_doc}
                    )
                    updated_count += 1
                else:
                    # Insert new listing with URL as _id
                    insert_doc = listing.copy()
                    insert_doc['_id'] = oid
                    insert_doc['first_seen'] = current_time
                    insert_doc['last_seen'] = current_time
                    insert_doc['scraped_at'] = current_time
                    insert_doc['deleted'] = False
                    
                    self.collection.insert_one(insert_doc)
                    inserted_count += 1
                    
            except Exception as e:
                print(f"✗ Error upserting listing {listing.get('url', 'unknown')}: {e}")
                error_count += 1
        
        print(f"✓ Inserted: {inserted_count}, Updated: {updated_count}, Errors: {error_count}")
        return {'inserted': inserted_count, 'updated': updated_count, 'errors': error_count}
    
    # READ operations
    
    def get_listing_by_id(self, listing_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single listing by its ID
        
        Args:
            listing_id: MongoDB document ID or custom listing ID
            
        Returns:
            Listing dictionary or None if not found
        """
        if not self._connected:
            print("✗ Not connected to database")
            return None
        
        try:
            from bson.objectid import ObjectId
            # Try to find by MongoDB _id first
            try:
                result = self.collection.find_one({"_id": ObjectId(listing_id)})
                if result:
                    return result
            except:
                pass
            
            # Try to find by custom listing_id field
            result = self.collection.find_one({"listing_id": listing_id})
            return result
        except Exception as e:
            print(f"✗ Error retrieving listing: {e}")
            return None
    
    def get_all_listings(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieve all listings from the database
        
        Args:
            limit: Maximum number of listings to return (None for all)
            
        Returns:
            List of listing dictionaries
        """
        if not self._connected:
            print("✗ Not connected to database")
            return []
        
        try:
            cursor = self.collection.find()
            if limit:
                cursor = cursor.limit(limit)
            return list(cursor)
        except Exception as e:
            print(f"✗ Error retrieving listings: {e}")
            return []
    
    def find_listings(self, query: Dict[str, Any], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Find listings matching a query
        
        Args:
            query: MongoDB query dictionary
            limit: Maximum number of results to return
            
        Returns:
            List of matching listing dictionaries
        """
        if not self._connected:
            print("✗ Not connected to database")
            return []
        
        try:
            cursor = self.collection.find(query)
            if limit:
                cursor = cursor.limit(limit)
            return list(cursor)
        except Exception as e:
            print(f"✗ Error finding listings: {e}")
            return []
    
    # UPDATE operations
    
    def update_listing(self, listing_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update a single listing
        
        Args:
            listing_id: MongoDB document ID or custom listing ID
            update_data: Dictionary containing fields to update
            
        Returns:
            True if update successful, False otherwise
        """
        if not self._connected:
            print("✗ Not connected to database")
            return False
        
        try:
            from bson.objectid import ObjectId
            # Add update timestamp
            update_data['updated_at'] = datetime.utcnow()
            
            # Try to update by MongoDB _id first
            try:
                result = self.collection.update_one(
                    {"_id": ObjectId(listing_id)},
                    {"$set": update_data}
                )
                if result.modified_count > 0:
                    return True
            except:
                pass
            
            # Try to update by custom listing_id field
            result = self.collection.update_one(
                {"listing_id": listing_id},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"✗ Error updating listing: {e}")
            return False
    
    def update_listings(self, query: Dict[str, Any], update_data: Dict[str, Any]) -> int:
        """
        Update multiple listings matching a query
        
        Args:
            query: MongoDB query dictionary to match documents
            update_data: Dictionary containing fields to update
            
        Returns:
            Number of documents updated
        """
        if not self._connected:
            print("✗ Not connected to database")
            return 0
        
        try:
            # Add update timestamp
            update_data['updated_at'] = datetime.utcnow()
            
            result = self.collection.update_many(
                query,
                {"$set": update_data}
            )
            return result.modified_count
        except Exception as e:
            print(f"✗ Error updating listings: {e}")
            return 0
    
    # DELETE operations
    
    def delete_listing(self, listing_id: str) -> bool:
        """
        Delete a single listing
        
        Args:
            listing_id: MongoDB document ID or custom listing ID
            
        Returns:
            True if deletion successful, False otherwise
        """
        if not self._connected:
            print("✗ Not connected to database")
            return False
        
        try:
            from bson.objectid import ObjectId
            # Try to delete by MongoDB _id first
            try:
                result = self.collection.delete_one({"_id": ObjectId(listing_id)})
                if result.deleted_count > 0:
                    return True
            except:
                pass
            
            # Try to delete by custom listing_id field
            result = self.collection.delete_one({"listing_id": listing_id})
            return result.deleted_count > 0
        except Exception as e:
            print(f"✗ Error deleting listing: {e}")
            return False
    
    def delete_listings(self, query: Dict[str, Any]) -> int:
        """
        Delete multiple listings matching a query
        
        Args:
            query: MongoDB query dictionary to match documents
            
        Returns:
            Number of documents deleted
        """
        if not self._connected:
            print("✗ Not connected to database")
            return 0
        
        try:
            result = self.collection.delete_many(query)
            return result.deleted_count
        except Exception as e:
            print(f"✗ Error deleting listings: {e}")
            return 0
    
    def delete_all_listings(self) -> int:
        """
        Delete all listings from the collection (use with caution!)
        
        Returns:
            Number of documents deleted
        """
        if not self._connected:
            print("✗ Not connected to database")
            return 0
        
        try:
            result = self.collection.delete_many({})
            print(f"✓ Deleted {result.deleted_count} listings")
            return result.deleted_count
        except Exception as e:
            print(f"✗ Error deleting all listings: {e}")
            return 0
    
    # Utility operations
    
    def count_listings(self, query: Optional[Dict[str, Any]] = None) -> int:
        """
        Count listings in the database
        
        Args:
            query: Optional query to filter count
            
        Returns:
            Number of listings
        """
        if not self._connected:
            print("✗ Not connected to database")
            return 0
        
        try:
            if query:
                return self.collection.count_documents(query)
            return self.collection.count_documents({})
        except Exception as e:
            print(f"✗ Error counting listings: {e}")
            return 0
    
    def create_index(self, field: str, unique: bool = False) -> bool:
        """
        Create an index on a field
        
        Args:
            field: Field name to index
            unique: Whether the index should enforce uniqueness
            
        Returns:
            True if index created successfully
        """
        if not self._connected:
            print("✗ Not connected to database")
            return False
        
        try:
            self.collection.create_index([(field, 1)], unique=unique)
            print(f"✓ Created index on field: {field}")
            return True
        except Exception as e:
            print(f"✗ Error creating index: {e}")
            return False
    
    def cleanup_old_listings(self, days_threshold: int = 2) -> int:
        """
        Mark listings as deleted if not seen in the specified number of days
        
        Args:
            days_threshold: Number of days (default: 2)
            
        Returns:
            Number of listings marked as deleted
        """
        if not self._connected:
            print("✗ Not connected to database")
            return 0
        
        try:
            from datetime import timedelta
            
            # Calculate threshold date
            threshold_date = datetime.utcnow() - timedelta(days=days_threshold)
            
            # Find listings not seen since threshold and not already marked as deleted
            query = {
                'last_seen': {'$lt': threshold_date},
                '$or': [
                    {'deleted': {'$exists': False}},
                    {'deleted': False}
                ]
            }
            
            # Mark as deleted
            result = self.collection.update_many(
                query,
                {
                    '$set': {
                        'deleted': True,
                        'deleted_at': datetime.utcnow()
                    }
                }
            )
            
            count = result.modified_count
            if count > 0:
                print(f"✓ Marked {count} listings as deleted (not seen in {days_threshold}+ days)")
            else:
                print(f"✓ No listings to mark as deleted")
            
            return count
            
        except Exception as e:
            print(f"✗ Error cleaning up old listings: {e}")
            return 0
