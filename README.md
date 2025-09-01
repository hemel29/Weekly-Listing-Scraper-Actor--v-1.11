# Property Listing Management System

This system automates the process of checking, adding, and updating property listings between a website and Airtable database.

## Features

### 1. Check and Add New Properties
- Checks the first property from the website
- If it exists in Airtable, no new properties are added
- If not found, continues adding new properties until a match is found
- Automatically extracts Development Name and ListingURL for each property
- Uploads new properties to Airtable in batches

### 2. Update Existing Properties
- Compares specific fields between website and Airtable for each property
- Only updates mismatched fields, preserving all other data
- Fields checked for updates:
  - Developer information
  - Property type
  - Block and Units Details
  - Expected completion (EXP Top)
  - Address
  - Location
  - Country
  - Tenure information

### 3. Full Details Scraper
- Extracts comprehensive property information including:
  - Description images
  - Site plan images
  - Elevation chart images
  - Gallery images
  - Floor plan images
  - Videos and virtual tour links

## Installation

1. Install required dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure Chrome browser is installed for Selenium automation

3. Configure Airtable credentials in the script files:
   - `AIRTABLE_API_KEY`
   - `AIRTABLE_BASE_ID`
   - `AIRTABLE_TABLE_ID`

## Usage

### Option 1: Interactive Menu
Run the main script for an interactive menu:
```bash
python main.py
```

Choose from:
1. Check and add new properties
2. Update existing properties
3. Run both operations
4. Run full details scraper

### Option 2: Direct Function Calls
Import and use specific functions:

```python
import check_new_listings

# Check and add new properties
check_new_listings.check_and_add_new_properties(headless=True, batch_size=16)

# Update existing properties
check_new_listings.update_existing_properties(headless=True)
```

### Option 3: Individual Scripts
Run individual components:

```bash
# Check and add new properties
python check_new_listings.py

# Run full details scraper
python get_full_details.py
```

## Configuration

### Airtable Setup
- Create a base with a table for property listings
- Ensure the table has fields for:
  - Development Name (text)
  - ListingURL (url)
  - Developer (text)
  - Type (text)
  - Block and Units Details (text)
  - EXP Top (text)
  - Address (text)
  - Location (text)
  - Country (text)
  - Tenure (text)

### Website Configuration
- Update the `URL` variable in `check_new_listings.py` to point to your property listing website
- Ensure the website uses the expected CSS selectors:
  - `.projectBox` for property cards
  - `.projectBoxImg img` for property images
  - `.client-box` for property details
  - `.description-box` for descriptions
  - `.gallery-box` for image galleries

## Workflow

### Adding New Properties
1. System checks first property on website
2. Compares with Airtable records
3. If no match found, continues adding properties
4. Stops when an existing property is encountered
5. Uploads all new properties to Airtable

### Updating Existing Properties
1. Fetches all Airtable records with ListingURL
2. Visits each property's detail page
3. Extracts current field values
4. Compares with Airtable values
5. Updates only mismatched fields

### Full Details Extraction
1. Processes properties missing detailed information
2. Extracts comprehensive media and text content
3. Updates Airtable with rich content
4. Handles images, videos, and virtual tours

## Error Handling

- Automatic retry mechanisms for failed requests
- Graceful handling of missing elements
- Detailed logging of all operations
- Continues processing even if individual properties fail

## Performance

- Batch processing for Airtable operations
- Configurable batch sizes
- Polite delays between requests
- Headless browser operation for efficiency

## Monitoring

The system provides detailed console output including:
- Progress indicators
- Success/failure counts
- Field change details
- Processing statistics

## Troubleshooting

### Common Issues
1. **Chrome driver not found**: Ensure Chrome is installed and accessible
2. **Airtable API errors**: Check API key and permissions
3. **Website changes**: Verify CSS selectors are still valid
4. **Rate limiting**: Adjust delays between requests

### Debug Mode
Set `headless=False` in function calls to see browser operations in real-time.

## Security Notes

- API keys are stored in the script files
- Consider using environment variables for production
- Ensure proper access controls on Airtable bases
- Monitor API usage to avoid rate limits

## Support

For issues or questions:
1. Check console output for error messages
2. Verify Airtable configuration
3. Test website accessibility
4. Review browser console for JavaScript errors
