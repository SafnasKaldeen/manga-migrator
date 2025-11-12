# Cloudinary Migration Setup

This guide will help you migrate your manga images from one Cloudinary account to another using GitHub Actions.

## 📋 Features

- ✅ **Resume Support**: Automatically resumes from where it left off if 6-hour timeout is reached
- ✅ **Smart Skip**: Only migrates images that aren't already in destination
- ✅ **Progress Tracking**: Maintains a CSV log of all migrations
- ✅ **Automatic Retry**: Scheduled runs automatically retry failed migrations
- ✅ **Folder Structure**: Preserves your manga/slug/chapter-XXX structure

## 🚀 Setup Instructions

### 1. Repository Structure

Organize your files like this:

```
your-repo/
├── .github/
│   └── workflows/
│       └── migrate.yml          # GitHub Actions workflow
├── scripts/
│   ├── migrate_cloudinary.py    # Migration script
│   └── migration_log.csv        # Auto-generated progress log
└── README.md
```

### 2. GitHub Secrets Configuration

Go to your repository's **Settings → Secrets and variables → Actions** and add these secrets:

#### Source Cloudinary (OLD account)

- `SOURCE_CLOUDINARY_CLOUD_NAME`
- `SOURCE_CLOUDINARY_API_KEY`
- `SOURCE_CLOUDINARY_API_SECRET`

#### Destination Cloudinary (NEW account)

- `DEST_CLOUDINARY_CLOUD_NAME`
- `DEST_CLOUDINARY_API_KEY`
- `DEST_CLOUDINARY_API_SECRET`

### 3. Files to Create

#### Create `scripts/migrate_cloudinary.py`

Copy the migration script provided.

#### Create `.github/workflows/migrate.yml`

Copy the workflow YAML provided.

## 🎮 Usage

### Option 1: Manual Trigger (Recommended for First Run)

1. Go to **Actions** tab in your GitHub repository
2. Select **Cloudinary Migration** workflow
3. Click **Run workflow**
4. Choose:
   - Leave empty to migrate **all manga**
   - Enter manga slug to migrate **specific manga** (e.g., `solo-leveling`)

### Option 2: Automatic Schedule

The workflow runs automatically every 6 hours to:

- Resume incomplete migrations
- Retry failed images
- Process any new content

You can modify the schedule in the workflow file:

```yaml
schedule:
  - cron: "0 */6 * * *" # Every 6 hours
```

## 📊 Monitoring Progress

### View Live Progress

- Go to **Actions** tab
- Click on the running workflow
- Expand the "☁️ Run migration" step to see real-time progress

### Check Migration Log

After each run, the workflow:

1. Uploads `migration_log.csv` as an artifact
2. Commits it back to the repository

Download the log to see:

- Timestamp of each migration
- Source and destination paths
- Success/failure status
- Error messages (if any)

### Migration Statistics

The workflow automatically displays statistics at the end:

```
📊 Migration Statistics:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total processed: 1000
✅ Success: 980
❌ Failed: 10
⏭️  Skipped: 10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 🔄 How Resume Works

1. **First Run**: Starts migrating all images
2. **Timeout Reached**: Workflow stops at 5h 50min mark
3. **Next Run**: Automatically triggered after 6 hours
4. **Resume**: Checks `migration_log.csv` and skips already-migrated images
5. **Continue**: Picks up where it left off
6. **Repeat**: Until all images are migrated

## 🛠️ Troubleshooting

### High Failure Rate

- Check if destination Cloudinary has enough storage
- Verify API credentials are correct
- Check rate limits on both accounts

### Workflow Timeout

- This is expected for large collections
- The workflow will automatically resume
- Each run processes ~5 hours of migration

### Duplicate Images

- The script uses `overwrite=False`
- Existing images are skipped automatically
- Check `migration_log.csv` for status

### Re-run Failed Images

Simply trigger the workflow again. It will:

- Skip successful migrations
- Retry failed ones
- Update the log

## 📈 Performance

- **Speed**: ~500 images per hour (depends on image sizes)
- **Rate Limiting**: Built-in delays to respect API limits
- **Efficiency**: Downloads from source, uploads to destination in memory

## 🧪 Testing

### Test with a Single Manga

```bash
# Run locally for testing
cd scripts
export SOURCE_CLOUDINARY_CLOUD_NAME="your_source"
export SOURCE_CLOUDINARY_API_KEY="your_key"
export SOURCE_CLOUDINARY_API_SECRET="your_secret"
export DEST_CLOUDINARY_CLOUD_NAME="your_dest"
export DEST_CLOUDINARY_API_KEY="your_key"
export DEST_CLOUDINARY_API_SECRET="your_secret"

python migrate_cloudinary.py solo-leveling
```

### Verify Migration

After migration, check destination Cloudinary:

1. Log into new Cloudinary account
2. Navigate to Media Library
3. Check `manga/` folder
4. Verify folder structure is preserved
5. Spot-check some images

## 💡 Tips

1. **Start Small**: Test with one manga first
2. **Monitor First Run**: Watch the logs to ensure it's working
3. **Check Logs Regularly**: Review `migration_log.csv` for issues
4. **Be Patient**: Large collections take time
5. **Trust the Process**: The resume feature works automatically

## 🔒 Security

- Never commit credentials to repository
- Always use GitHub Secrets
- Regularly rotate API keys
- Review workflow permissions

## 📞 Support

If you encounter issues:

1. Check the workflow logs
2. Review `migration_log.csv`
3. Verify all secrets are set correctly
4. Ensure both Cloudinary accounts are active

---

**Note**: This migration is **non-destructive**. Your source Cloudinary remains unchanged. You can delete source content manually after verifying the migration is successful.
