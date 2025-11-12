#!/usr/bin/env python3
"""
Cloudinary to Cloudinary Migration Script
Migrates manga images from source to destination Cloudinary account
Supports resume on timeout - skips already migrated images
"""

import os
import sys
import csv
import time
import requests
from datetime import datetime
import cloudinary
import cloudinary.uploader
import cloudinary.api
from urllib.parse import urlparse

# ============================================
# CONFIGURATION
# ============================================

# Source Cloudinary (old account)
SOURCE_CONFIG = {
    'cloud_name': os.environ.get('SOURCE_CLOUDINARY_CLOUD_NAME'),
    'api_key': os.environ.get('SOURCE_CLOUDINARY_API_KEY'),
    'api_secret': os.environ.get('SOURCE_CLOUDINARY_API_SECRET')
}

# Destination Cloudinary (new account)
DEST_CONFIG = {
    'cloud_name': os.environ.get('DEST_CLOUDINARY_CLOUD_NAME'),
    'api_key': os.environ.get('DEST_CLOUDINARY_API_KEY'),
    'api_secret': os.environ.get('DEST_CLOUDINARY_API_SECRET')
}

MIGRATION_LOG = "migration_log.csv"
CLOUDINARY_BASE = "manga"

# Try to find existing metadata CSV
METADATA_CSV_PATHS = [
    "cloudinary_manga_metadata.csv",
    "../cloudinary_manga_metadata.csv",
    "scripts/cloudinary_manga_metadata.csv"
]

def find_metadata_csv():
    """Find the metadata CSV file"""
    for path in METADATA_CSV_PATHS:
        if os.path.exists(path):
            return path
    return METADATA_CSV_PATHS[0]  # Default to first option

# ============================================
# DUAL CLOUDINARY CLIENT
# ============================================

class CloudinaryClient:
    """Wrapper to switch between source and destination accounts"""
    
    @staticmethod
    def configure_source():
        cloudinary.config(**SOURCE_CONFIG)
    
    @staticmethod
    def configure_dest():
        cloudinary.config(**DEST_CONFIG)


# ============================================
# MIGRATION LOG MANAGEMENT
# ============================================

def load_migration_log():
    """Load already migrated images from log"""
    migrated = set()
    
    if not os.path.exists(MIGRATION_LOG):
        return migrated
    
    try:
        with open(MIGRATION_LOG, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['status'] == 'success':
                    # Store full path: manga/slug/chapter-001/panel-001
                    migrated.add(row['source_path'])
    except Exception as e:
        print(f"⚠️  Could not load migration log: {e}")
    
    return migrated


def log_migration(source_path, dest_path, status, error=''):
    """Log migration result"""
    
    # Create log file if doesn't exist
    if not os.path.exists(MIGRATION_LOG):
        with open(MIGRATION_LOG, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'source_path', 'dest_path', 
                'status', 'error'
            ])
    
    # Append result
    with open(MIGRATION_LOG, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            source_path,
            dest_path,
            status,
            error
        ])


# ============================================
# CLOUDINARY RESOURCE FETCHING
# ============================================

def get_all_resources_from_source(folder_prefix):
    """
    Get all resources from source Cloudinary under a folder prefix
    Returns list of resources with their metadata
    """
    print(f"🔍 Fetching resources from source: {folder_prefix}")
    
    CloudinaryClient.configure_source()
    
    all_resources = []
    next_cursor = None
    
    try:
        while True:
            # Fetch resources with pagination
            result = cloudinary.api.resources(
                type='upload',
                prefix=folder_prefix,
                max_results=500,  # Max allowed per request
                next_cursor=next_cursor
            )
            
            resources = result.get('resources', [])
            all_resources.extend(resources)
            
            print(f"  📦 Fetched {len(resources)} resources (total: {len(all_resources)})")
            
            next_cursor = result.get('next_cursor')
            if not next_cursor:
                break
            
            time.sleep(0.5)  # Rate limit protection
    
    except Exception as e:
        print(f"❌ Error fetching resources: {e}")
        return []
    
    print(f"✅ Total resources found: {len(all_resources)}")
    return all_resources


# ============================================
# IMAGE MIGRATION
# ============================================

def migrate_image(resource, already_migrated):
    """
    Migrate a single image from source to destination
    Returns: (success, error_message)
    """
    
    public_id = resource.get('public_id')
    folder = resource.get('folder', '')
    secure_url = resource.get('secure_url')
    format_type = resource.get('format', 'jpg')
    
    # Check if already migrated
    if public_id in already_migrated:
        return True, "already_migrated"
    
    try:
        # Download from source
        print(f"  📥 Downloading from source...", end='', flush=True)
        CloudinaryClient.configure_source()
        
        response = requests.get(secure_url, timeout=30)
        response.raise_for_status()
        image_data = response.content
        file_size_kb = len(image_data) / 1024
        print(f" {file_size_kb:.1f}KB", flush=True)
        
        # Upload to destination
        print(f"  📤 Uploading to destination...", end='', flush=True)
        CloudinaryClient.configure_dest()
        
        # Ensure folder exists in destination
        if folder:
            try:
                cloudinary.api.create_folder(folder)
            except:
                pass  # Folder might already exist
        
        # Upload with same public_id and folder structure
        upload_result = cloudinary.uploader.upload(
            image_data,
            public_id=public_id,
            overwrite=False,
            resource_type="auto",
            use_filename=False,
            unique_filename=False
        )
        
        dest_url = upload_result.get('secure_url')
        print(f" Done! ✅", flush=True)
        
        return True, ""
        
    except Exception as e:
        print(f" Failed! ❌", flush=True)
        return False, str(e)


# ============================================
# MAIN MIGRATION LOGIC
# ============================================

def migrate_manga_folder(manga_slug=None):
    """
    Migrate all manga images from source to destination
    If manga_slug provided, only migrate that manga
    Otherwise migrate entire manga/ folder
    """
    
    print("="*80)
    print("  ☁️  CLOUDINARY MIGRATION SCRIPT")
    print("="*80)
    
    # Determine folder prefix
    if manga_slug:
        folder_prefix = f"{CLOUDINARY_BASE}/{manga_slug}"
        print(f"\n📚 Migrating specific manga: {manga_slug}")
    else:
        folder_prefix = CLOUDINARY_BASE
        print(f"\n📚 Migrating entire manga collection")
    
    print(f"📁 Folder prefix: {folder_prefix}\n")
    
    # Load migration log
    already_migrated = load_migration_log()
    print(f"✅ Already migrated: {len(already_migrated)} images\n")
    
    # Get all resources from source
    resources = get_all_resources_from_source(folder_prefix)
    
    if not resources:
        print("❌ No resources found to migrate")
        return {
            'success': False,
            'error': 'No resources found'
        }
    
    # Filter out already migrated
    to_migrate = [r for r in resources if r.get('public_id') not in already_migrated]
    
    print(f"\n📊 Migration Plan:")
    print(f"  Total images in source: {len(resources)}")
    print(f"  Already migrated: {len(already_migrated)}")
    print(f"  To migrate: {len(to_migrate)}")
    print()
    
    if len(to_migrate) == 0:
        print("✨ All images already migrated!")
        return {
            'success': True,
            'migrated': 0,
            'skipped': len(resources),
            'failed': 0
        }
    
    # Migrate images
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    print(f"🚀 Starting migration...\n")
    
    for idx, resource in enumerate(to_migrate, 1):
        public_id = resource.get('public_id')
        
        # Extract readable info
        parts = public_id.split('/')
        display_name = '/'.join(parts[-3:]) if len(parts) >= 3 else public_id
        
        try:
            success, error = migrate_image(resource, already_migrated)
            
            if success:
                if error == "already_migrated":
                    print(f"⏭️  [{idx}/{len(to_migrate)}] Skipped: {display_name}")
                    skipped_count += 1
                    log_migration(public_id, public_id, 'skipped', 'already_migrated')
                else:
                    print(f"✅ [{idx}/{len(to_migrate)}] Migrated: {display_name}")
                    success_count += 1
                    log_migration(public_id, public_id, 'success', '')
                    already_migrated.add(public_id)
            else:
                print(f"❌ [{idx}/{len(to_migrate)}] Failed: {display_name}")
                print(f"   Error: {error[:100]}")
                failed_count += 1
                log_migration(public_id, public_id, 'failed', error)
            
            # Rate limiting
            time.sleep(0.5)
            
            # Progress update every 50 images
            if idx % 50 == 0:
                print(f"\n📊 Progress: {idx}/{len(to_migrate)} processed")
                print(f"   ✅ Success: {success_count} | ❌ Failed: {failed_count} | ⏭️  Skipped: {skipped_count}\n")
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Migration interrupted by user")
            raise
        except Exception as e:
            print(f"❌ [{idx}/{len(to_migrate)}] Unexpected error: {str(e)[:100]}")
            failed_count += 1
            log_migration(public_id, public_id, 'failed', str(e))
    
    # Final summary
    print("\n" + "="*80)
    print("  📊 MIGRATION SUMMARY")
    print("="*80)
    print(f"✅ Successfully migrated: {success_count}")
    print(f"⏭️  Skipped (already migrated): {skipped_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"📄 Log file: {MIGRATION_LOG}")
    print("="*80 + "\n")
    
    return {
        'success': True,
        'migrated': success_count,
        'skipped': skipped_count,
        'failed': failed_count
    }


# ============================================
# MAIN ENTRY POINT
# ============================================

def main():
    """Main entry point for GitHub Actions"""
    
    # Validate environment variables
    required_vars = [
        'SOURCE_CLOUDINARY_CLOUD_NAME', 'SOURCE_CLOUDINARY_API_KEY', 'SOURCE_CLOUDINARY_API_SECRET',
        'DEST_CLOUDINARY_CLOUD_NAME', 'DEST_CLOUDINARY_API_KEY', 'DEST_CLOUDINARY_API_SECRET'
    ]
    
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
    
    # Optional: specific manga slug from command line
    manga_slug = sys.argv[1] if len(sys.argv) > 1 else None
    
    try:
        result = migrate_manga_folder(manga_slug)
        
        if result['success']:
            print("✅ Migration completed successfully!")
            sys.exit(0)
        else:
            print(f"❌ Migration failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n⚠️  Migration interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()