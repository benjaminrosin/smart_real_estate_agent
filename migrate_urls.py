"""
Migration script to clean URLs and update _id field
Removes query parameters from URLs and handles duplicates
"""
from dotenv import load_dotenv
from scraper.db_manager import MongoDBManager
from datetime import datetime
from collections import defaultdict

load_dotenv()


def clean_url(url: str) -> str:
    """Remove query parameters from URL"""
    if not url:
        return url
    return url.split('?')[0]


def merge_listings(listings: list) -> dict:
    """
    Merge multiple listings of the same property
    Keeps most recent data and merges features
    """
    if len(listings) == 1:
        return listings[0]
    
    # Sort by last_seen or scraped_at to get most recent
    listings.sort(key=lambda x: x.get('last_seen', x.get('scraped_at', datetime.min)), reverse=True)
    
    # Start with most recent listing
    merged = listings[0].copy()
    
    # Merge features from all listings
    all_features = set()
    for listing in listings:
        if 'features' in listing and listing['features']:
            all_features.update(listing['features'])
    
    if all_features:
        merged['features'] = list(all_features)
    
    # Keep earliest first_seen if available
    first_seen_dates = [l.get('first_seen') for l in listings if l.get('first_seen')]
    if first_seen_dates:
        merged['first_seen'] = min(first_seen_dates)
    
    # Keep most recent last_seen
    last_seen_dates = [l.get('last_seen', l.get('scraped_at')) for l in listings if l.get('last_seen') or l.get('scraped_at')]
    if last_seen_dates:
        merged['last_seen'] = max(last_seen_dates)
    
    return merged


def migrate_urls():
    """Main migration function"""
    print("=" * 80)
    print("URL Migration Script")
    print("=" * 80)
    print()
    
    # Connect to database
    db = MongoDBManager()
    if not db.connect(collection_name="listings"):
        print("✗ Failed to connect to database")
        return
    
    try:
        # Get all documents
        print("Fetching all documents...")
        all_listings = db.get_all_listings()
        total_docs = len(all_listings)
        print(f"Found {total_docs} documents")
        
        if total_docs == 0:
            print("No documents to migrate")
            return
        
        # Group by clean URL
        print("\nGrouping documents by clean URL...")
        url_groups = defaultdict(list)
        
        for listing in all_listings:
            old_url = listing.get('url', '')
            clean = clean_url(old_url)
            if clean:
                url_groups[clean].append(listing)
        
        total_unique = len(url_groups)
        total_duplicates = total_docs - total_unique
        
        print(f"Unique URLs: {total_unique}")
        print(f"Duplicates found: {total_duplicates}")
        
        if total_duplicates > 0:
            print(f"\nMerging {total_duplicates} duplicate listings...")
        
        # Create new collection for migrated data
        temp_collection_name = "listings_migrated"
        print(f"\nCreating temporary collection: {temp_collection_name}")
        db.db.drop_collection(temp_collection_name)
        temp_collection = db.db[temp_collection_name]
        
        # Process each URL group
        migrated_count = 0
        error_count = 0
        
        print("\nMigrating documents...")
        for clean_url_str, listings in url_groups.items():
            try:
                # Merge if there are duplicates
                if len(listings) > 1:
                    merged_listing = merge_listings(listings)
                    print(f"  Merged {len(listings)} duplicates for: {clean_url_str[:60]}...")
                else:
                    merged_listing = listings[0].copy()
                
                # Update URL and set _id
                merged_listing['url'] = clean_url_str
                merged_listing['_id'] = clean_url_str
                merged_listing['migrated_at'] = datetime.utcnow()
                
                # Ensure deleted field exists
                if 'deleted' not in merged_listing:
                    merged_listing['deleted'] = False
                
                # Insert into temp collection
                temp_collection.insert_one(merged_listing)
                migrated_count += 1
                
            except Exception as e:
                print(f"  ✗ Error migrating {clean_url_str}: {e}")
                error_count += 1
        
        print(f"\nMigrated {migrated_count} documents")
        if error_count > 0:
            print(f"Errors: {error_count}")
        
        # Confirm before swapping collections
        print("\n" + "=" * 80)
        print("READY TO SWAP COLLECTIONS")
        print("=" * 80)
        print(f"Original collection: {total_docs} documents")
        print(f"New collection: {migrated_count} documents")
        print(f"Documents that will be removed: {total_duplicates}")
        print()
        
        response = input("Proceed with migration? (yes/no): ").strip().lower()
        
        if response == 'yes':
            print("\nSwapping collections...")
            
            # Backup old collection
            backup_collection_name = f"listings_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            print(f"Creating backup: {backup_collection_name}")
            db.db["listings"].aggregate([{"$out": backup_collection_name}])
            
            # Drop old collection
            print("Dropping old collection...")
            db.db.drop_collection("listings")
            
            # Rename temp to listings
            print("Renaming temporary collection to 'listings'...")
            temp_collection.aggregate([{"$out": "listings"}])
            
            # Drop temp collection
            db.db.drop_collection(temp_collection_name)
            
            print("\n" + "=" * 80)
            print("✓ MIGRATION COMPLETE!")
            print("=" * 80)
            print(f"Original documents: {total_docs}")
            print(f"Migrated documents: {migrated_count}")
            print(f"Duplicates removed: {total_duplicates}")
            print(f"Backup saved as: {backup_collection_name}")
            print("=" * 80)
        else:
            print("\nMigration cancelled. Cleaning up temporary collection...")
            db.db.drop_collection(temp_collection_name)
            print("✓ Cleanup complete")
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.disconnect()


if __name__ == "__main__":
    migrate_urls()
