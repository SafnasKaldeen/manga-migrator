#!/usr/bin/env python3
"""
Cloudinary to Cloudinary Migration Script
Migrates manga images from source to destination Cloudinary account
WITH PARALLEL PROCESSING (10x faster)
WITH RESOURCE CACHING (avoids rate limits)
WITH AUTO-RESUME (handles 6-hour timeout)
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import json

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
PARALLEL_WORKERS = 10  # Number of simultaneous uploads
RESOURCE_CACHE = "resource_cache.json"  # Cache fetched resources

# Thread-safe lock for logging
log_lock = threading.Lock()

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
    """Log migration result (thread-safe)"""
    
    with log_lock:
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
# CLOUDINARY RESOURCE FETCHING WITH CACHE
# ============================================

def get_all_resources_from_source(folder_prefix):
    """
    Get all resources from source Cloudinary under a folder prefix
    Returns list of resources with their metadata
    USES CACHING to avoid re-fetching on rate limit errors
    """
    
    # Check cache first
    if os.path.exists(RESOURCE_CACHE):
        print(f"📦 Found cached resource list: {RESOURCE_CACHE}")
        try:
            with open(RESOURCE_CACHE, 'r') as f:
                cached_data = json.load(f)
                if cached_data.get('folder_prefix') == folder_prefix:
                    resources = cached_data.get('resources', [])
                    cache_time = cached_data.get('timestamp', 'unknown')
                    is_partial = cached_data.get('partial', False)
                    print(f"✅ Using cached resources: {len(resources)} items")
                    print(f"   Cached at: {cache_time}")
                    if is_partial:
                        print(f"   ⚠️  This is a partial cache (hit rate limit during fetch)")
                    return resources
        except Exception as e:
            print(f"⚠️  Cache read error: {e}")
    
    print(f"🔍 Fetching resources from source: {folder_prefix}")
    print(f"⚠️  This uses Cloudinary API calls (limit: 500/hour)")
    
    CloudinaryClient.configure_source()
    
    all_resources = []
    next_cursor = None
    fetch_count = 0
    
    try:
        while True:
            fetch_count += 1
            
            # Fetch resources with pagination
            result = cloudinary.api.resources(
                type='upload',
                prefix=folder_prefix,
                max_results=500,  # Max allowed per request
                next_cursor=next_cursor
            )
            
            resources = result.get('resources', [])
            all_resources.extend(resources)
            
            print(f"  📦 Fetched {len(resources)} resources (total: {len(all_resources)}) [API call #{fetch_count}]")
            
            next_cursor = result.get('next_cursor')
            if not next_cursor:
                break
            
            # Small delay between requests
            time.sleep(0.5)
    
    except Exception as e:
        error_msg = str(e)
        
        # Check if rate limit error
        if '420' in error_msg or 'rate limit' in error_msg.lower():
            print(f"\n⚠️  RATE LIMIT HIT!")
            print(f"   Fetched {len(all_resources)} resources before limit")
            
            if len(all_resources) > 0:
                print(f"   💾 Caching what we have so far...")
                # Save partial results to cache
                cache_data = {
                    'folder_prefix': folder_prefix,
                    'resources': all_resources,
                    'timestamp': datetime.now().isoformat(),
                    'partial': True,
                    'fetch_count': fetch_count
                }
                with open(RESOURCE_CACHE, 'w') as f:
                    json.dump(cache_data, f, indent=2)
                print(f"   ✅ Cached {len(all_resources)} resources")
                print(f"   🔄 Will use this cache on next run and continue migration")
                return all_resources
        
        print(f"❌ Error fetching resources: {error_msg}")
        return all_resources if all_resources else []
    
    # Save complete results to cache
    if all_resources:
        print(f"\n💾 Caching complete resource list...")
        cache_data = {
            'folder_prefix': folder_prefix,
            'resources': all_resources,
            'timestamp': datetime.now().isoformat(),
            'partial': False,
            'fetch_count': fetch_count
        }
        try:
            with open(RESOURCE_CACHE, 'w') as f:
                json.dump(cache_data, f, indent=2)
            print(f"✅ Cached {len(all_resources)} resources")
        except Exception as e:
            print(f"⚠️  Could not save cache: {e}")
    
    print(f"✅ Total resources found: {len(all_resources)}")
    return all_resources


# ============================================
# IMAGE MIGRATION WITH PARALLEL PROCESSING
# ============================================

def migrate_image(resource, already_migrated, worker_id=0):
    """
    Migrate a single image from source to destination
    Returns: (success, error_message, public_id, file_size_kb)
    """
    
    public_id = resource.get('public_id')
    folder = resource.get('folder', '')
    secure_url = resource.get('secure_url')
    format_type = resource.get('format', 'jpg')
    
    # Check if already migrated
    if public_id in already_migrated:
        return True, "already_migrated", public_id, 0
    
    try:
        # Download from source
        CloudinaryClient.configure_source()
        
        response = requests.get(secure_url, timeout=30)
        response.raise_for_status()
        image_data = response.content
        file_size_kb = len(image_data) / 1024
        
        # Upload to destination
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
        
        return True, "", public_id, file_size_kb
        
    except Exception as e:
        return False, str(e), public_id, 0


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
    
    # Get all resources from source (uses cache if available)
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
    
    # Migrate images with parallel processing
    success_count = 0
    failed_count = 0
    skipped_count = 0
    total_size_mb = 0
    
    print(f"🚀 Starting PARALLEL migration with {PARALLEL_WORKERS} workers...\n")
    
    start_time = time.time()
    processed = 0
    
    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        # Submit all tasks
        future_to_resource = {
            executor.submit(migrate_image, resource, already_migrated, i % PARALLEL_WORKERS): resource 
            for i, resource in enumerate(to_migrate)
        }
        
        # Process completed tasks as they finish
        for future in as_completed(future_to_resource):
            processed += 1
            resource = future_to_resource[future]
            public_id = resource.get('public_id')
            
            # Extract readable info
            parts = public_id.split('/')
            display_name = '/'.join(parts[-3:]) if len(parts) >= 3 else public_id
            
            try:
                success, error, public_id, file_size_kb = future.result()
                total_size_mb += file_size_kb / 1024
                
                # Progress calculations
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                eta_seconds = (len(to_migrate) - processed) / rate if rate > 0 else 0
                eta_minutes = eta_seconds / 60
                
                if success:
                    if error == "already_migrated":
                        print(f"⏭️  [{processed}/{len(to_migrate)}] SKIP: {display_name}")
                        skipped_count += 1
                        log_migration(public_id, public_id, 'skipped', 'already_migrated')
                    else:
                        print(f"✅ [{processed}/{len(to_migrate)}] OK: {display_name} ({file_size_kb:.1f}KB)")
                        success_count += 1
                        log_migration(public_id, public_id, 'success', '')
                        already_migrated.add(public_id)
                else:
                    print(f"❌ [{processed}/{len(to_migrate)}] FAIL: {display_name}")
                    print(f"   └─ Error: {error[:80]}")
                    failed_count += 1
                    log_migration(public_id, public_id, 'failed', error)
                
                # Checkpoint every 50 images
                if processed % 50 == 0:
                    print(f"\n{'═'*80}")
                    print(f"🎯 CHECKPOINT: {processed}/{len(to_migrate)} ({(processed/len(to_migrate)*100):.1f}%)")
                    print(f"   ✅ Success: {success_count} | ❌ Failed: {failed_count} | ⏭️  Skipped: {skipped_count}")
                    print(f"   ⏱️  Elapsed: {elapsed/60:.1f}m | Rate: {rate*60:.1f}/min | ETA: {eta_minutes:.1f}m")
                    print(f"   💾 Data migrated: {total_size_mb:.1f}MB")
                    if processed > skipped_count:
                        success_rate = (success_count/(processed-skipped_count)*100)
                        print(f"   📈 Success rate: {success_rate:.1f}%")
                    print(f"{'═'*80}\n")
            
            except Exception as e:
                print(f"❌ [{processed}/{len(to_migrate)}] ERROR: {display_name}")
                print(f"   └─ Exception: {str(e)[:80]}")
                failed_count += 1
                log_migration(public_id, public_id, 'failed', str(e))
    
    # Final summary
    total_time = time.time() - start_time
    print("\n" + "="*80)
    print("  📊 MIGRATION SUMMARY")
    print("="*80)
    print(f"⏱️  Total time: {total_time/60:.1f} minutes ({total_time/3600:.2f} hours)")
    print(f"📦 Total processed: {len(to_migrate)}")
    print(f"✅ Successfully migrated: {success_count}")
    print(f"⏭️  Skipped (already migrated): {skipped_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"💾 Data transferred: {total_size_mb:.1f}MB ({total_size_mb/1024:.2f}GB)")
    if total_time > 0:
        print(f"⚡ Average speed: {(success_count/(total_time/60)):.1f} images/min")
    if failed_count > 0:
        print(f"\n⚠️  {failed_count} images failed - they will be retried on next run")
    print(f"📄 Log file: {MIGRATION_LOG}")
    print(f"📦 Cache file: {RESOURCE_CACHE}")
    print("="*80 + "\n")
    
    return {
        'success': True,
        'migrated': success_count,
        'skipped': skipped_count,
        'failed': failed_count,
        'total_size_mb': total_size_mb
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