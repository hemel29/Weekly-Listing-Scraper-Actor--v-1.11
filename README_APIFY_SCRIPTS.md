# Apify Scripts Usage Guide

This guide explains how to use the Property Listing Management System with Apify.

## Overview

The system now automatically runs both main operations without interactive input:
1. **Check and add new properties** - Scans for new properties and adds them to Airtable
2. **Update existing properties** - Updates existing property information

## Main Actor (Property Listing Management)

### Available Operations
- **Check and add new properties** - Scans for new properties and adds them to Airtable
- **Update existing properties** - Updates existing property information  
- **Run both operations** - Executes both operations in sequence (default)

### Method 1: Actor Input (Recommended)

**Using Actor Input in Apify Console:**
1. Go to your actor's main page
2. Click "Start" 
3. In the "Input" section, you'll see a form with these options:
   - **Operation to Run**: Dropdown with options:
     - "1. Check and add new properties"
     - "2. Update existing properties" 
     - "3. Run both operations" (default)
   - **Batch Size**: Number of records per batch (1-50, default: 16)
   - **Headless Mode**: Run browser in headless mode (default: true)

### Method 2: Environment Variables (Fallback)

If Actor Input is not available, it falls back to:
- `APIFY_OPERATION=check_new` or `APIFY_OPERATION=1` - Check and add new properties
- `APIFY_OPERATION=update` or `APIFY_OPERATION=2` - Update existing properties
- `APIFY_OPERATION=both` or `APIFY_OPERATION=3` - Run both operations (default)

**Default behavior:** If no input is provided, it runs both operations.

## Separate Actor: Full Details Scraper

The **Full Details Scraper** is now a separate actor located in the `full_details_actor/` directory.

### Setup
1. The `full_details_actor/` directory is ready to deploy
2. Deploy the `full_details_actor/` directory as a separate Apify actor
3. Run when you need to scrape full property details

### Usage
- No input configuration needed - it runs automatically
- Focused solely on full details scraping functionality

## Local Development

The main script now runs both operations automatically:

```bash
# Runs both operations automatically (no interactive input)
python main.py
```

Or test the Apify selector locally:

```bash
# Test with Actor Input file
APIFY_INPUT_FILE=test_input.json python apify_selector.py

# Test with environment variable (fallback)
APIFY_OPERATION=update python apify_selector.py
```

## Benefits of This Approach

1. **No Interactive Input Required** - Scripts run automatically
2. **Simplified Operations** - Focus on the two main operations
3. **Separate Concerns** - Full details scraper is a separate actor
4. **Environment Variable Support** - Can be configured in Apify
5. **Actor Input Support** - User-friendly interface in Apify console

## File Structure

```
├── main.py                    # Main entry point (runs both operations)
├── apify_selector.py          # Apify selector with Actor Input support
├── check_new_listings.py      # Main scraping logic
├── .actor/
│   └── input_schema.json      # Actor Input schema
├── full_details_actor/        # Separate actor for full details scraper
│   ├── main.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── README.md
└── README_APIFY_SCRIPTS.md    # This file
```

## Troubleshooting

If you encounter issues:
1. Make sure you're using the correct actor (main vs full_details_actor)
2. Check that your Dockerfile CMD points to the right script
3. Verify Actor Input configuration or environment variables
4. Check Chrome options for containerized environments