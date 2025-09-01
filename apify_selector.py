#!/usr/bin/env python3
"""
Apify Script Selector (COMMENTED OUT FOR LOCAL DEVELOPMENT)
This file is kept for reference but not used in local development
"""

# Apify-specific imports (commented out for local development)
# import os
# import sys
# import json
import check_new_listings

# def get_actor_input():
#     """Get Actor Input from Apify, fallback to environment variables"""
#     try:
#         # Try to read from Actor Input (Apify standard)
#         input_file = os.getenv('APIFY_INPUT_FILE', '/apify/input.json')
#         if os.path.exists(input_file):
#             with open(input_file, 'r') as f:
#                 actor_input = json.load(f)
#                 print(f"📥 Using Actor Input: {actor_input}")
#                 return actor_input
#     except Exception as e:
#         print(f"⚠️ Could not read Actor Input: {e}")
#     
#     # Fallback to environment variables
#     print("📥 Using environment variables as fallback")
#     return {
#         'operation': os.getenv('APIFY_OPERATION', 'check_new').strip().lower(),
#         'batch_size': int(os.getenv('APIFY_BATCH_SIZE', '16')),
#         'headless': os.getenv('APIFY_HEADLESS', 'true').lower() == 'true'
#     }

def main():
    print("🚀 Local Development Mode - Running Both Operations")
    
    # Run both operations automatically (local development approach)
    print("\n🆕 Step 1: Check and add new properties...")
    check_new_listings.check_and_add_new_properties(headless=True, batch_size=16)
    
    print("\n" + "="*50)
    print("\n🔄 Step 2: Update existing properties...")
    check_new_listings.update_existing_properties(headless=True)
    
    print("\n✅ Both operations completed successfully!")

    # Original Apify logic (commented out for local development)
    # config = get_actor_input()
    # operation = config.get('operation', 'both').strip().lower()
    # batch_size = config.get('batch_size', 16)
    # headless = config.get('headless', True)
    #
    # print(f"🚀 Apify Property Listing Management System")
    # print(f"Selected operation: {operation}")
    # print(f"Batch size: {batch_size}")
    # print(f"Headless mode: {headless}")
    #
    # if operation == "check_new" or operation == "1":
    #     print("🆕 Running: Check and add new properties...")
    #     import check_new_listings
    #     check_new_listings.check_and_add_new_properties(headless=headless, batch_size=batch_size)
    #
    # elif operation == "update" or operation == "2":
    #     print("🔄 Running: Update existing properties...")
    #     import check_new_listings
    #     check_new_listings.update_existing_properties(headless=headless)
    #
    # elif operation == "both" or operation == "3" or operation == "default":
    #     print("🚀 Running: Both operations...")
    #     import check_new_listings
    #     check_new_listings.check_and_add_new_properties(headless=headless, batch_size=batch_size)
    #     print("\n" + "="*50)
    #     check_new_listings.update_existing_properties(headless=headless)
    #
    # else:
    #     print(f"❌ Invalid operation '{operation}'. Available options:")
    #     print("  - check_new, 1: Check and add new properties")
    #     print("  - update, 2: Update existing properties")
    #     print("  - both, 3: Run both operations (default)")
    #     print("Defaulting to 'both'...")
    #     import check_new_listings
    #     check_new_listings.check_and_add_new_properties(headless=headless, batch_size=batch_size)
    #     print("\n" + "="*50)
    #     check_new_listings.update_existing_properties(headless=headless)
    #
    # print("\n✅ Apify run completed successfully!")

if __name__ == "__main__":
    main()
