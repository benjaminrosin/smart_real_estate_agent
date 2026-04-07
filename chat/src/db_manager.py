"""
MongoDB Database Manager for Chat Bot Users
Handles connection and CRUD operations for user data
"""
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from typing import Dict, Optional, Any
from datetime import datetime
import os


class UserDBManager:
    """Manager class for MongoDB user operations"""
    
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
            raise ValueError("MongoDB connection string not provided. Set MONGO_URI environment variable.")
        
        self.database_name = database_name
        self.client = None
        self.db = None
        self.collection = None
        self._connected = False
        
    def connect(self, collection_name: str = "users") -> bool:
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
            
            # Create unique index on chat_id
            self.collection.create_index("chat_id", unique=True)
            
            self._connected = True
            print(f"✓ Connected to MongoDB - Database: {self.database_name}, Collection: {collection_name}")
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
    
    def register_user(self, chat_id: int, first_name: str, last_name: Optional[str] = None, 
                      username: Optional[str] = None) -> Dict[str, Any]:
        """
        Register a new user or update existing user on /start
        
        Args:
            chat_id: Telegram chat ID (unique identifier)
            first_name: User's first name from Telegram
            last_name: User's last name from Telegram (optional)
            username: User's @username from Telegram (optional)
            
        Returns:
            User document (existing or newly created)
        """
        if not self._connected:
            raise RuntimeError("Not connected to database. Call connect() first.")
        
        now = datetime.utcnow()
        
        # Check if user exists
        existing_user = self.get_user(chat_id)
        
        if existing_user:
            # Update last_seen and Telegram profile info
            self.collection.update_one(
                {"chat_id": chat_id},
                {
                    "$set": {
                        "first_name": first_name,
                        "last_name": last_name,
                        "username": username,
                        "last_seen": now
                    }
                }
            )
            existing_user["last_seen"] = now
            return existing_user
        else:
            # Create new user
            new_user = {
                "chat_id": chat_id,
                "first_name": first_name,
                "last_name": last_name,
                "username": username,
                "display_name": first_name,  # Default display name
                "registered_at": now,
                "last_seen": now,
                "settings": {}
            }
            self.collection.insert_one(new_user)
            print(f"✓ Registered new user: {first_name} (chat_id: {chat_id})")
            return new_user
    
    def get_user(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user by Telegram chat ID
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            User document or None if not found
        """
        if not self._connected:
            raise RuntimeError("Not connected to database. Call connect() first.")
        
        return self.collection.find_one({"chat_id": chat_id})
    
    def update_user(self, chat_id: int, updates: Dict[str, Any]) -> bool:
        """
        Update user profile fields
        
        Args:
            chat_id: Telegram chat ID
            updates: Dictionary of fields to update
            
        Returns:
            True if update successful, False otherwise
        """
        if not self._connected:
            raise RuntimeError("Not connected to database. Call connect() first.")
        
        # Add updated timestamp
        updates["updated_at"] = datetime.utcnow()
        
        result = self.collection.update_one(
            {"chat_id": chat_id},
            {"$set": updates}
        )
        
        return result.modified_count > 0
    
    def user_exists(self, chat_id: int) -> bool:
        """
        Check if user is registered
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            True if user exists, False otherwise
        """
        if not self._connected:
            raise RuntimeError("Not connected to database. Call connect() first.")
        
        return self.collection.count_documents({"chat_id": chat_id}) > 0
