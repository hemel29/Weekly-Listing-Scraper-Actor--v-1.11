import check_new_listings
# import os  # Commented out - not needed for local development

def main():
    print("Property Listing Management System")
    print("🚀 Running both operations automatically...")
    
    # Apify-specific code (commented out for local development)
    # if os.getenv('APIFY_OPERATION'):
    #     print(f"\n🚀 Apify mode detected. Using APIFY_OPERATION={os.getenv('APIFY_OPERATION')}")
    #     import apify_selector
    #     apify_selector.main()
    #     return

    # Local development mode - run both operations automatically
    print("\n🆕 Step 1: Check and add new properties...")
    check_new_listings.check_and_add_new_properties(headless=True, batch_size=16)
    
    print("\n" + "="*50)
    print("\n🔄 Step 2: Update existing properties...")
    check_new_listings.update_existing_properties(headless=True)
    
    print("\n✅ Both operations completed successfully!")

if __name__ == "__main__":
    main()

