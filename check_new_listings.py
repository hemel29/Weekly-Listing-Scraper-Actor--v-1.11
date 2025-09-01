# if not in airtable then scrape name and listing url

import requests
import time, json
# import os  # Commented out - not needed for local development
# import uuid  # Commented out - not needed for local development
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

URL = "https://share.ecoprop.com/R062972G?VNK=32f530c3"

# Airtable config

AIRTABLE_API_KEY = "pat2WsZZK3mMRPkua.51d5ffef9db33b0b866b55870f74343ae70d132f2481f1af2de5456b5622bd50"
AIRTABLE_BASE_ID = "app79G4gcDC3l2f4g"
AIRTABLE_TABLE_ID = "tblLu03udJ2S5fptj"
# Use table ID consistently - this is the correct format for Airtable API v0
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json"
}

# Fields to check for updates
UPDATE_FIELDS = [
    "Developer",           # Developer information
    "Type",                # Property type
    "Block and Units Details", # Unit details
    "EXP Top",             # Expected completion
    "Address",             # Full address
    "Location",            # Location
    "Country",             # Country
    "Tenure"               # Tenure information
]

def make_driver(headless=True):
    opts = Options()
    
    # Basic options that work perfectly for local development
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    else:
        opts.add_argument("--start-maximized")
    
    # Apify-specific options (commented out for local development)
    # unique_id = str(uuid.uuid4())[:8]
    # user_data_dir = f"/tmp/chrome-user-data-{unique_id}"
    # opts.add_argument("--disable-web-security")
    # opts.add_argument("--disable-features=VizDisplayCompositor")
    # opts.add_argument("--remote-debugging-port=9222")
    # opts.add_argument(f"--user-data-dir={user_data_dir}")
    # opts.add_argument("--disable-extensions")
    # opts.add_argument("--disable-plugins")
    # opts.add_argument("--disable-background-timer-throttling")
    # opts.add_argument("--disable-backgrounding-occluded-windows")
    # opts.add_argument("--disable-renderer-backgrounding")
    
    return webdriver.Chrome(service=Service(), options=opts)

def wait_for_spinners_gone(driver, timeout=10):
    try:
        WebDriverWait(driver, timeout).until_not(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".van-loading__circular"))
        )
    except TimeoutException:
        pass

def wait_for_navigation(driver, old_url, old_handles, timeout=25):
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.current_url != old_url or len(d.window_handles) != len(old_handles)
        )
    except TimeoutException:
        pass
    if len(driver.window_handles) > len(old_handles):
        new_handle = list(set(driver.window_handles) - set(old_handles))[0]
        driver.switch_to.window(new_handle)

def _find_scroll_container(driver):
    return driver.execute_script("""
        const els = Array.from(document.querySelectorAll('*'));
        for (const el of els) {
            const cs = getComputedStyle(el);
            if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
                return el;
            }
        }
        return null;
    """)

def _try_click_load_more(driver):
    xps = [
        "//button[contains(translate(., 'LOAD MORE', 'load more'), 'load more')]",
        "//div[contains(translate(., 'LOAD MORE', 'load more'), 'load more')]",
        "//span[contains(translate(., 'LOAD MORE', 'load more'), 'load more')]",
        "//button[contains(translate(., 'MORE', 'more'), 'more')]"
    ]
    for xp in xps:
        for b in driver.find_elements(By.XPATH, xp):
            try:
                if b.is_displayed() and b.is_enabled():
                    b.click()
                    return True
            except Exception:
                pass
    return False

def scroll_until_count(driver, target_count=100, max_rounds=600, step=1200, pause=0.5):
    """
    Keep scrolling the proper container until we have at least target_count cards
    or growth stalls. Returns the final list of .projectBox elements.
    """
    container = _find_scroll_container(driver)
    last_count, stagnant = 0, 0

    for r in range(max_rounds):
        cards = driver.find_elements(By.CSS_SELECTOR, ".projectBox")
        count = len(cards)
        if count >= target_count:
            print(f"✅ Reached {count} cards (target {target_count})")
            break

        if container:
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + arguments[1];", container, step)
        else:
            driver.execute_script("window.scrollBy(0, arguments[0]);", step)

        if cards:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'end'});", cards[-1])
            except Exception:
                pass

        wait_for_spinners_gone(driver, timeout=5)
        time.sleep(pause)

        if r % 5 == 4:
            if container:
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", container)
            else:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(pause)

        _try_click_load_more(driver)

        new_count = len(driver.find_elements(By.CSS_SELECTOR, ".projectBox"))
        print(f"🔽 Scroll {r+1}: {new_count} cards")
        if new_count <= last_count:
            stagnant += 1
            if stagnant >= 6:
                print("ℹ️ No further growth; stopping scroll.")
                break
        else:
            stagnant = 0
        last_count = new_count

    return driver.find_elements(By.CSS_SELECTOR, ".projectBox")

def click_record_image(driver, img, index_1_based, clickable_timeout=12):
    xpath = f"(//div[contains(@class,'projectBoxImg')]//img)[{index_1_based}]"
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", img)
    WebDriverWait(driver, clickable_timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
    wait_for_spinners_gone(driver, timeout=10)
    parent = img.find_element(By.XPATH, "./ancestor::div[contains(@class,'projectBoxImg')]")
    driver.execute_script("arguments[0].click();", parent)

def extract_projectbox(card):
    data = {}
    
    try:
        # Debug: Print card HTML structure to understand what we're working with
        print(f"🔍 Debug: Card HTML structure preview:")
        try:
            card_html = card.get_attribute('outerHTML')[:500]  # First 500 chars
            print(f"   HTML preview: {card_html}...")
        except Exception as e:
            print(f"   Could not get HTML: {e}")
        
        print(f"   Card text preview: {card.text[:200]}...")
        # Try multiple selectors for images
        img_selectors = [
            ".projectBoxImg img",
            ".project-box img",
            ".property-card img", 
            ".listing-card img",
            ".card img",
            "img"
        ]
        
        imgs = []
        for selector in img_selectors:
            try:
                imgs = card.find_elements(By.CSS_SELECTOR, selector)
                if imgs:
                    break
            except Exception:
                continue
        
        data["image_srcs"] = [i.get_attribute("src") for i in imgs if i.get_attribute("src")]
        
        # Try multiple selectors for tags
        tag_selectors = [
            ".van-tag",
            ".tag",
            ".label",
            ".badge",
            "[class*='tag']",
            "[class*='label']"
        ]
        
        tags = []
        for selector in tag_selectors:
            try:
                tags = card.find_elements(By.CSS_SELECTOR, selector)
                if tags:
                    break
            except Exception:
                continue
        
        data["tags"] = [t.text.strip() for t in tags if t.text.strip()]
        
        # Try multiple selectors for title - prioritize more specific ones
        title_selectors = [
            ".projectBox .title",           # Most specific - project box title
            ".projectBox .name",            # Project box name
            ".projectBox h1",               # Project box heading
            ".projectBox h2",               # Project box subheading
            ".projectBox h3",               # Project box subheading
            ".projectBox .custom-title",    # Custom title class
            ".projectBox [class*='title']", # Any class containing 'title'
            ".projectBox [class*='name']",  # Any class containing 'name'
            ".title",                       # Fallback to general title
            ".name",                        # Fallback to general name
            "h1", "h2", "h3", "h4", "h5", "h6",  # Any heading
            "[class*='title']",            # Any class containing 'title'
            "[class*='name']"              # Any class containing 'name'
        ]
        
        title_el = None
        for selector in title_selectors:
            try:
                title_el = card.find_elements(By.CSS_SELECTOR, selector)
                if title_el and title_el[0].text.strip():
                    print(f"   ✅ Found title with selector: {selector}")
                    print(f"   📝 Title text: '{title_el[0].text.strip()}'")
                    break
                elif title_el:
                    print(f"   ⚠️ Selector '{selector}' found elements but no text")
            except Exception as e:
                print(f"   ❌ Selector '{selector}' failed: {e}")
                continue
        
        if title_el and title_el[0].text.strip():
            data["title"] = title_el[0].text.strip()
        else:
            print(f"   🔍 No title found with standard selectors, trying fallback...")
            # Fallback: try to find any text that looks like a title
            try:
                # Look for the largest text element in the card
                all_text_elements = card.find_elements(By.CSS_SELECTOR, "*")
                largest_text = ""
                for elem in all_text_elements:
                    text = elem.text.strip()
                    if text and len(text) > len(largest_text) and len(text) < 100:
                        # Avoid very long text (likely descriptions)
                        if not any(word in text.lower() for word in ["street", "road", "avenue", "drive", "place", "apartment", "house"]):
                            largest_text = text
                
                if largest_text:
                    data["title"] = largest_text
                else:
                    data["title"] = ""
            except Exception:
                data["title"] = ""
        
        # Try multiple selectors for location
        location_selectors = [
            ".van-cell:has(.van-icon-location-o)",
            ".cell:has(.icon-location)",
            ".info:has(.location)",
            "[class*='location']",
            "[class*='address']"
        ]
        
        data["location"] = ""
        for selector in location_selectors:
            try:
                loc_cell = card.find_elements(By.CSS_SELECTOR, selector)
                if loc_cell:
                    spans = loc_cell[0].find_elements(By.CSS_SELECTOR, "span")
                    if spans:
                        data["location"] = spans[0].text.strip()
                        break
            except Exception:
                continue
        
        # If no location found with complex selectors, try simpler approach
        if not data["location"]:
            try:
                # Look for any text that might contain location info
                all_text = card.text.lower()
                if any(word in all_text for word in ["street", "road", "avenue", "drive", "place"]):
                    # Try to find the element containing this text
                    for element in card.find_elements(By.XPATH, ".//*[contains(text(), 'Street') or contains(text(), 'Road') or contains(text(), 'Avenue')]"):
                        if element.text.strip():
                            data["location"] = element.text.strip()
                            break
            except Exception:
                pass
        
        # Try multiple selectors for property type
        type_selectors = [
            ".textBox .van-cell",
            ".info .cell",
            ".details .row",
            "[class*='type']",
            "[class*='category']"
        ]
        
        prop_type = ""
        for selector in type_selectors:
            try:
                cells = card.find_elements(By.CSS_SELECTOR, selector)
                if cells:
                    # Look for property type in the cells
                    for cell in cells:
                        cell_text = cell.text.lower()
                        if any(word in cell_text for word in ["apartment", "house", "villa", "condo", "townhouse", "penthouse"]):
                            prop_type = cell.text.strip()
                            break
                    if prop_type:
                        break
            except Exception:
                continue
        
        data["property_type"] = prop_type
        
        # Try multiple selectors for links
        link_selectors = [
            "a[href]",
            "[class*='link']",
            "[class*='button']"
        ]
        
        links = []
        for selector in link_selectors:
            try:
                links = card.find_elements(By.CSS_SELECTOR, selector)
                if links:
                    break
            except Exception:
                continue
        
        data["links_in_card"] = [a.get_attribute("href") for a in links if a.get_attribute("href")]
        data["full_text"] = card.text.strip()
        
    except Exception as e:
        print(f"⚠️ Error extracting data from card: {e}")
        # Return minimal data to prevent crashes
        data = {
            "image_srcs": [],
            "tags": [],
            "title": "",
            "location": "",
            "property_type": "",
            "links_in_card": [],
            "full_text": card.text.strip() if card else ""
        }
    
    return data

def airtable_headers():
    return {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}

def airtable_batch_create(records):
    """Send records in chunks of 10. Returns number of records successfully created."""
    success = 0
    for i in range(0, len(records), 10):
        chunk = {"records": records[i:i+10]}
        time.sleep(0.3)
        for attempt in range(5):
            r = requests.post(AIRTABLE_URL, headers=airtable_headers(), json=chunk, timeout=30)
            if r.status_code == 429:
                wait = min(2 ** attempt, 8)
                print(f"⚠️ Airtable 429, retrying in {wait}s...")
                time.sleep(wait)
                continue
            if r.status_code in (200, 201):
                print(f"✅ Airtable batch created ({len(chunk['records'])})")
                success += len(chunk["records"])
            else:
                print(f"❌ Airtable error ({r.status_code}): {r.text}")
            break
    return success





def get_first_airtable_properties():
    params = {
        "pageSize": 1,
        "sort[0][field]": "Order",
        "sort[0][direction]": "asc"
    }

    try:
        print("🔍 Fetching first Airtable properties...")
        response = requests.get(AIRTABLE_URL, headers=HEADERS, params=params)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch Airtable properties: {response.status_code}")
            print(f"📄 Response text: {response.text}")
            return []
        
        data = response.json()
        records_info = [
            {
                "Development Name": record["fields"].get("Development Name", ""),
                "Created Time": record["fields"].get("Created Time", ""),
                "ListingURL": record["fields"].get("ListingURL", "")
            }
            for record in data.get("records", [])
        ]

        for i, record in enumerate(records_info, 1):
            print(f"{i}. {record['Development Name']} - Created on {record['Created Time']}")

        return records_info
        
    except Exception as e:
        print(f"❌ Exception during Airtable API call: {e}")
        return []




def get_airtable_records(limit=10, ascending=True):
    params = {
        "pageSize": limit,
        "sort[0][field]": "Order",
        "sort[0][direction]": "asc" if ascending else "desc"
    }

    try:
        print(f"🔍 Fetching Airtable records (limit: {limit}, ascending: {ascending})...")
        response = requests.get(AIRTABLE_URL, headers=HEADERS, params=params)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch Airtable records: {response.status_code}")
            print(f"📄 Response text: {response.text}")
            return []
        
        data = response.json()
        records_info = [
            {
                "Development Name": record["fields"].get("Development Name", ""),
                "Created Time": record["fields"].get("Created Time", ""),
                "ListingURL": record["fields"].get("ListingURL", "")
            }
            for record in data.get("records", [])
        ]

        label = "Top 10" if ascending else "Last 10"
        print(f"\n🔹 {label} Records by Order:")
        for i, record in enumerate(records_info, 1):
            print(f"{i}. {record['Development Name']} - Created on {record['Created Time']}")

        return records_info
        
    except Exception as e:
        print(f"❌ Exception during Airtable API call: {e}")
        return []







def get_airtable_records_by_development_name(development_name):
    """Get Airtable records by Development Name field"""
    params = {
        "filterByFormula": "{Development Name} = '" + development_name.replace("'", "\\'") + "'",
        "pageSize": 100
    }
    
    try:
        print(f"🔍 Searching Airtable for: '{development_name}'")
        print(f"🔗 API URL: {AIRTABLE_URL}")
        print(f"📝 Filter formula: {params['filterByFormula']}")
    
        response = requests.get(AIRTABLE_URL, headers=HEADERS, params=params)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch Airtable records: {response.status_code}")
            print(f"📄 Response text: {response.text}")
            return []
        
        data = response.json()
        record_count = len(data.get("records", []))
        print(f"✅ Found {record_count} records in Airtable")
        
        # Show details of what was found
        if record_count > 0:
            print("📋 Records found:")
            for i, record in enumerate(data.get("records", [])):
                dev_name = record.get("fields", {}).get("Development Name", "NO_NAME")
                listing_url = record.get("fields", {}).get("ListingURL", "NO_URL")
                record_id = record.get("id", "NO_ID")
                print(f"   Record {i+1}: ID={record_id}, Name='{dev_name}', URL='{listing_url}'")
                
                # Check if this is an exact match
                if dev_name.strip() == development_name.strip():
                    print(f"   ✅ EXACT MATCH: '{dev_name}' == '{development_name}'")
                else:
                    print(f"   ❌ NO EXACT MATCH: '{dev_name}' != '{development_name}'")
        
        return data.get("records", [])
        
    except Exception as e:
        print(f"❌ Exception during Airtable API call: {e}")
        return []

def check_and_add_new_properties(headless=True, batch_size=16):
    """
    Check first property from website. If it exists in Airtable, no need to add more.
    If not, add properties with all details until there's a match.
    """
    driver = make_driver(headless=headless)
    
    try:
        # Get first property from website
        print("Loading website...")
        driver.get(URL)
        wait_for_spinners_gone(driver, timeout=20)
        
        # Wait for page to fully load and look for property cards
        print("⏳ Waiting for property cards to load...")
        max_wait_attempts = 30
        first_card = None
        
        for attempt in range(max_wait_attempts):
            try:
                # Try multiple selectors for property cards
                selectors = [
                    ".projectBox",
                    ".project-box", 
                    ".property-card",
                    ".listing-card",
                    ".card",
                    "[class*='project']",
                    "[class*='property']"
                ]
                
                for selector in selectors:
                    try:
                        cards = driver.find_elements(By.CSS_SELECTOR, selector)
                        if cards:
                            first_card = cards[0]
                            print(f"✅ Found property cards using selector: {selector}")
                            break
                    except Exception:
                        continue
                
                if first_card:
                    break
                    
                # If no cards found, try scrolling to trigger lazy loading
                driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)
                
                if attempt % 5 == 0:
                    print(f"   Attempt {attempt + 1}/{max_wait_attempts}: Waiting for content...")
                    
            except Exception as e:
                if attempt % 5 == 0:
                    print(f"   Attempt {attempt + 1}/{max_wait_attempts}: {e}")
                time.sleep(1)
        
        if not first_card:
            print("❌ Could not find any property cards after multiple attempts.")
            print("   Please check if the website structure has changed.")
            return
        
        # Scroll to first card and wait for it to be fully loaded
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_card)
        wait_for_spinners_gone(driver, timeout=20)
        
        # Extract first property data
        try:
            first_data = extract_projectbox(first_card)
            first_dev_name = (first_data.get("title") or "").strip()
            
            if not first_dev_name:
                print("❌ Could not extract property name from first card.")
                return
                
        except Exception as e:
            print(f"❌ Failed to extract data from first card: {e}")
            return
        
        print(f"\n🌐 First property on website: {first_dev_name}")
        
        # Check if first property exists in Airtable
        print("🔍 Checking if property exists in Airtable...")
        existing_records = get_airtable_records_by_development_name(first_dev_name)
        
        if existing_records:
            print(f"✅ First property '{first_dev_name}' already exists in Airtable. No new properties to add.")
            return
        
        print(f"🆕 First property '{first_dev_name}' not found in Airtable. Starting to add new properties...")
        
        # Continue adding properties until we find a match
        idx = 0
        new_props = []
        
        while True:
            # Re-find cards to avoid stale elements
            cards_now = []
            for selector in [".projectBox", ".project-box", ".property-card", ".listing-card", ".card"]:
                try:
                    cards_now = driver.find_elements(By.CSS_SELECTOR, selector)
                    if cards_now:
                        break
                except Exception:
                    continue
            
            if idx >= len(cards_now):
                # Scroll to load more
                driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(2)
                
                # Re-find cards after scrolling
                for selector in [".projectBox", ".project-box", ".property-card", ".listing-card", ".card"]:
                    try:
                        cards_now = driver.find_elements(By.CSS_SELECTOR, selector)
                        if cards_now:
                            break
                    except Exception:
                        continue
                        
                if idx >= len(cards_now):
                    print("⚠️ No more property cards available.")
                    break
            
            card = cards_now[idx]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
            wait_for_spinners_gone(driver, timeout=20)
            
            try:
                data = extract_projectbox(card)
                dev_name = (data.get("title") or "").strip()
                
                if not dev_name:
                    print(f"[{idx + 1}] ⚠️ Skipping card with no title")
                    idx += 1
                    continue
                    
                print(f"[{idx + 1}] Processing: {dev_name}")
            except Exception as e:
                print(f"⚠️ Extract failed on card {idx + 1}: {e}")
                idx += 1
                continue
            
            # Check if this property exists in Airtable
            existing_records = get_airtable_records_by_development_name(dev_name)
            
            # Only consider it a match if there's an exact match in Development Name
            has_exact_match = False
            if existing_records:
                for record in existing_records:
                    airtable_name = record.get("fields", {}).get("Development Name", "").strip()
                    if airtable_name == dev_name:
                        has_exact_match = True
                        print(f"✅ Found exact match in Airtable: '{dev_name}'. Stopping addition.")
                        break
                
                if has_exact_match:
                    break
                else:
                    print(f"⚠️ Found {len(existing_records)} records but no exact match for '{dev_name}'. Continuing...")
            
            if has_exact_match:
                break
            
            # Get detail URL for this property
            detail_url = ""
            try:
                # Try multiple image selectors
                img_selectors = [
                    ".projectBoxImg img",
                    ".project-box img", 
                    ".property-card img",
                    ".listing-card img",
                    ".card img",
                    "img"
                ]
                
                img = None
                for img_selector in img_selectors:
                    try:
                        imgs = card.find_elements(By.CSS_SELECTOR, img_selector)
                        if imgs:
                            img = imgs[0]
                            break
                    except Exception:
                        continue
                
                if not img:
                    print(f"[{idx + 1}] ⚠️ No image found for {dev_name}")
                    idx += 1
                    continue
                
                old_url = driver.current_url
                old_handles = driver.window_handles[:]
                
                # Try to click the image to get detail URL
                try:
                    click_record_image(driver, img, index_1_based=idx + 1, clickable_timeout=15)
                    wait_for_navigation(driver, old_url, old_handles, timeout=25)
                    detail_url = driver.current_url
                except Exception as e:
                    print(f"[{idx + 1}] ⚠️ Click failed, trying alternative method...")
                    try:
                        # Alternative: try to find a link in the card
                        links = card.find_elements(By.CSS_SELECTOR, "a[href]")
                        if links:
                            detail_url = links[0].get_attribute("href")
                        else:
                            detail_url = ""
                    except Exception:
                        detail_url = ""
                
                # Go back to list
                try:
                    if len(driver.window_handles) > len(old_handles):
                        driver.close()
                        driver.switch_to.window(old_handles[0])
                    else:
                        driver.back()
                    wait_for_spinners_gone(driver, timeout=20)
                except Exception:
                    pass
                    
            except Exception as e:
                print(f"⚠️ Click/nav failed on card {idx + 1}: {e}")
                detail_url = ""
                try:
                    if len(driver.window_handles) > len(old_handles):
                        driver.close()
                        driver.switch_to.window(old_handles[0])
                    else:
                        driver.back()
                    wait_for_spinners_gone(driver, timeout=20)
                except Exception:
                    pass
            
            # Add to new properties list
            new_props.append({
                "fields": {
                    "Development Name": dev_name,
                    "ListingURL": detail_url
                }
            })
            
            print(f"[{idx + 1}] Added new property: {dev_name} -> {detail_url}")
            idx += 1
        
        # Upload new properties to Airtable
        if new_props:
            print(f"\n📤 Uploading {len(new_props)} new properties to Airtable...")
            
            total_sent = 0
            batch = []
            
            for record in new_props:
                batch.append(record)
                if len(batch) == batch_size:
                    created = airtable_batch_create(batch)
                    total_sent += created
                    print(f"➡️ Sent batch of {created}. Total sent: {total_sent}")
                    batch.clear()
            
            if batch:
                created = airtable_batch_create(batch)
                total_sent += created
                print(f"➡️ Sent final batch of {created}. Total sent: {total_sent}")
            
            print(f"\n🎉 Done. Total new properties uploaded: {total_sent}")
        else:
            print("\n🚫 No new properties to upload.")
    
    finally:
        time.sleep(0.3)
        driver.quit()

def update_existing_properties(headless=True):
    """
    Update logic: Match UPDATE_FIELDS values in Airtable and website for each property.
    If there's any mismatch, only update these values to Airtable. Keep all other values as is.
    """
    driver = make_driver(headless=headless)
    
    try:
        # Get all Airtable records that have ListingURL
        params = {
            "filterByFormula": "NOT({ListingURL} = BLANK())",
            "pageSize": 100
        }
        
        response = requests.get(AIRTABLE_URL, headers=HEADERS, params=params)
        if response.status_code != 200:
            print(f"❌ Failed to fetch Airtable records: {response.status_code}")
            return
        
        data = response.json()
        records = data.get("records", [])
        
        print(f"📋 Found {len(records)} records with ListingURL. Starting update process...")
        
        updated_count = 0
        
        for i, record in enumerate(records):
            record_id = record["id"]
            fields = record["fields"]
            development_name = fields.get("Development Name", "")
            listing_url = fields.get("ListingURL", "")
            
            if not listing_url:
                continue
            
            print(f"\nProcessing {i+1}: {development_name}")
            print(f"URL: {listing_url}")
            
            try:
                # Navigate to the listing URL
                driver.get(listing_url)
                wait_for_spinners_gone(driver, timeout=20)
                
                # Extract current website data for UPDATE_FIELDS
                website_data = {}
                
                # Extract project info (Developer, Type, etc.)
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".client-box"))
                    )
                    client_box = driver.find_element(By.CSS_SELECTOR, ".client-box")
                    rows = client_box.find_elements(By.CSS_SELECTOR, ".van-row")
                    
                    for row in rows:
                        try:
                            cols = row.find_elements(By.CSS_SELECTOR, ".van-col")
                            if len(cols) >= 2:
                                label = cols[0].text.strip()
                                value = cols[1].text.strip()
                                if label in UPDATE_FIELDS:
                                    website_data[label] = value
                        except:
                            continue
                except Exception as e:
                    print(f"⚠️ Failed to extract client-box: {e}")
                
                # Check for mismatches and prepare update
                fields_to_update = {}
                has_changes = False
                
                for field in UPDATE_FIELDS:
                    website_value = website_data.get(field, "").strip()
                    airtable_value = fields.get(field, "").strip()
                    
                    if website_value and website_value != airtable_value:
                        fields_to_update[field] = website_value
                        has_changes = True
                        print(f"  🔄 {field}: '{airtable_value}' → '{website_value}'")
                
                # Update Airtable if there are changes
                if has_changes:
                    update_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}/{record_id}"
                    update_payload = {"fields": fields_to_update}
                    
                    update_response = requests.patch(
                        update_url, 
                        headers=HEADERS, 
                        json=update_payload, 
                        timeout=60
                    )
                    
                    if update_response.status_code == 200:
                        print(f"  ✅ Updated {len(fields_to_update)} fields")
                        updated_count += 1
                    else:
                        print(f"  ❌ Update failed: {update_response.status_code}")
                else:
                    print(f"  ✅ No updates needed")
                
                # Polite delay between requests
                time.sleep(1)
                
            except Exception as e:
                print(f"  ❌ Error processing {development_name}: {e}")
                continue
        
        print(f"\n🎉 Update process completed. Updated {updated_count} records.")
    
    finally:
        time.sleep(0.3)
        driver.quit()

def debug_website_structure(headless=False):
    """
    Debug function to analyze website structure and find correct selectors
    """
    driver = make_driver(headless=headless)
    
    try:
        print("🔍 Debugging website structure...")
        driver.get(URL)
        wait_for_spinners_gone(driver, timeout=20)
        
        print("\n📋 Analyzing page structure...")
        
        # Wait a bit for content to load
        time.sleep(5)
        
        # Try to find any elements that might be property cards
        potential_selectors = [
            ".projectBox", ".project-box", ".property-card", ".listing-card", 
            ".card", ".item", ".listing", ".property", ".development"
        ]
        
        print("\n🔍 Searching for property card elements...")
        for selector in potential_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"✅ Found {len(elements)} elements with selector: {selector}")
                    if len(elements) > 0:
                        first_element = elements[0]
                        print(f"   First element text: {first_element.text[:100]}...")
                        print(f"   First element classes: {first_element.get_attribute('class')}")
                        
                        # Look for images
                        imgs = first_element.find_elements(By.CSS_SELECTOR, "img")
                        if imgs:
                            print(f"   Found {len(imgs)} images")
                            for i, img in enumerate(imgs[:3]):  # Show first 3
                                src = img.get_attribute("src")
                                print(f"     Image {i+1}: {src[:50] if src else 'No src'}...")
                        
                        # Look for links
                        links = first_element.find_elements(By.CSS_SELECTOR, "a[href]")
                        if links:
                            print(f"   Found {len(links)} links")
                            for i, link in enumerate(links[:3]):  # Show first 3
                                href = link.get_attribute("href")
                                text = link.text.strip()
                                print(f"     Link {i+1}: {text[:30]} -> {href[:50] if href else 'No href'}...")
                        
                        # Look for text elements
                        headings = first_element.find_elements(By.CSS_SELECTOR, "h1, h2, h3, h4, h5, h6")
                        if headings:
                            print(f"   Found {len(headings)} headings")
                            for i, heading in enumerate(headings[:3]):  # Show first 3
                                print(f"     Heading {i+1}: {heading.text.strip()[:50]}...")
                        
                        break
                else:
                    print(f"❌ No elements found with selector: {selector}")
            except Exception as e:
                print(f"⚠️ Error with selector {selector}: {e}")
        
        # Look for any elements with common property-related classes
        print("\n🔍 Searching for common property-related classes...")
        common_classes = ["project", "property", "listing", "card", "item", "development"]
        
        for class_name in common_classes:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, f"[class*='{class_name}']")
                if elements:
                    print(f"✅ Found {len(elements)} elements with class containing '{class_name}'")
                    if len(elements) > 0:
                        first_element = elements[0]
                        print(f"   First element classes: {first_element.get_attribute('class')}")
                        print(f"   First element text: {first_element.text[:100]}...")
            except Exception as e:
                print(f"⚠️ Error searching for class '{class_name}': {e}")
        
        # Look for any clickable elements
        print("\n🔍 Searching for clickable elements...")
        try:
            clickable = driver.find_elements(By.CSS_SELECTOR, "a, button, [onclick], [role='button']")
            if clickable:
                print(f"✅ Found {len(clickable)} clickable elements")
                for i, element in enumerate(clickable[:5]):  # Show first 5
                    tag = element.tag_name
                    text = element.text.strip()[:30]
                    classes = element.get_attribute("class")
                    print(f"   Clickable {i+1}: <{tag}> {text} (classes: {classes})")
        except Exception as e:
            print(f"⚠️ Error searching for clickable elements: {e}")
        
        # Show page source structure
        print("\n🔍 Page structure analysis...")
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            all_elements = body.find_elements(By.XPATH, ".//*")
            print(f"✅ Total elements on page: {len(all_elements)}")
            
            # Count elements by tag
            tag_counts = {}
            for element in all_elements:
                tag = element.tag_name
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            
            print("   Element counts by tag:")
            for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"     {tag}: {count}")
                
        except Exception as e:
            print(f"⚠️ Error analyzing page structure: {e}")
        
        print("\n🎯 Debug analysis complete!")
        print("   Use this information to update the selectors in the code.")
        
    finally:
        if not headless:
            input("\nPress Enter to close the browser...")
        driver.quit()


