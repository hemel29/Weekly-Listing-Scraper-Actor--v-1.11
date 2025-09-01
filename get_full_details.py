# This script updates missing details in existing Airtable records using scraping all into propertylisting
import time
import json
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urljoin
from urllib.parse import quote
import subprocess
import sys
import os
from urllib.parse import urlparse
from selenium.common.exceptions import TimeoutException




# AIRTABLE_API_KEY = "pat2WsZZK3mMRPkua.51d5ffef9db33b0b866b55870f74343ae70d132f2481f1af2de5456b5622bd50"
# AIRTABLE_BASE_ID = "app79G4gcDC3l2f4g"
# AIRTABLE_TABLE_NAME = "test"
# AIRTABLE_TABLE_ID = "tblrJX2sHD7sqxqAK"  
# AIRTABLE_VIEW_ID  = "viwbkhw7LOv03ehw6"
# AIRTABLE_LISTING_FIELD = "ListingURL" 
# VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v", ".m3u8", ".ts"}
# M3U_TYPES = {"application/vnd.apple.mpegurl", "application/x-mpegurl"}

AIRTABLE_API_KEY = "pat2WsZZK3mMRPkua.51d5ffef9db33b0b866b55870f74343ae70d132f2481f1af2de5456b5622bd50"
AIRTABLE_BASE_ID = "app79G4gcDC3l2f4g"
AIRTABLE_TABLE_NAME = "Property Listing"
AIRTABLE_TABLE_ID = "tblLu03udJ2S5fptj"  
# AIRTABLE_VIEW_ID  = "viwegaYlquPC7KgS5"  # This view doesn't exist
AIRTABLE_LISTING_FIELD = "ListingURL" 
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v", ".m3u8", ".ts"}
M3U_TYPES = {"application/vnd.apple.mpegurl", "application/x-mpegurl"}


opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-dev-shm-usage")


# AIRTABLE_TABLE_NAME = "full launch"
# AIRTABLE_BASE_ID = "app79G4gcDC3l2f4g"
# AIRTABLE_TABLE_ID = "tblLu03udJ2S5fptj"  
# AIRTABLE_VIEW_ID  = "viwwV6vh7mpFssOMY"

TARGET_FIELDS = [
    "Developer", "Type", "Block and Units Details", "EXP Top",
    "Address", "Location", "Country", "Tenure"
]

def iter_listing_urls_from_airtable(limit=None):
    """
    Yields (record_id, ListingURL) ONLY for records where Developer and Type are blank.
    If limit is None, yields all.
    """
    base = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

    # Only rows where Developer and Type are blank/whitespace AND ListingURL exists
    # formula = (
    #     "AND("
    #     "{Developer} = BLANK(),"
    #     "{Type} = BLANK(),"
    #     "NOT({ListingURL} = BLANK())"
    #     ")"
    # )
    
    # Process ALL records that have a ListingURL (removed Developer/Type restrictions)
    formula = "NOT({ListingURL} = BLANK())"


    params = {
        # "view": AIRTABLE_VIEW_ID,  # Removed - view doesn't exist
        "pageSize": 100,
        "filterByFormula": formula,
        # You can request only needed fields; ListingURL is enough here
        "fields[]": [AIRTABLE_LISTING_FIELD],
    }

    offset = None
    count = 0
    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(base, headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"[ERROR] Failed to fetch listing URLs: {resp.status_code} {resp.text}")
            break

        payload = resp.json()
        for rec in payload.get("records", []):
            fields = rec.get("fields", {})
            url = (fields.get(AIRTABLE_LISTING_FIELD) or "").strip()
            rec_id = rec.get("id")
            if url and rec_id:
                yield rec_id, url
                count += 1
                if limit is not None and count >= limit:
                    return

        offset = payload.get("offset")
        if not offset:
            break

def is_downloadable_video(url: str) -> bool:
    # reject non-usable schemes for Airtable
    if not url or url.startswith(("blob:", "data:")):
        return False

    # quick extension check
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return True

    # fallback: HEAD check for Content-Type
    try:
        r = requests.head(url, allow_redirects=True, timeout=8)
        ct = (r.headers.get("Content-Type") or "").lower()
        return ct.startswith("video/") or ct in M3U_TYPES
    except Exception:
        return False

def filter_video_assets(urls):
    seen = set()
    out = []
    for u in urls or []:
        if u in seen: 
            continue
        seen.add(u)
        if is_downloadable_video(u):
            out.append(u)
    return out

def wait_for_all_videos(driver, timeout=15):
    last_count = -1
    start = time.time()
    while time.time() - start < timeout:
        btns = driver.find_elements(By.CSS_SELECTOR, ".img-box .LinkBtn .VideoBtn")
        count = len(btns)
        if count > last_count:
            last_count = count
            time.sleep(0.5)  # wait a bit more, maybe more will load
        else:
            break  # no new buttons loaded
    return driver.find_elements(By.CSS_SELECTOR, ".img-box .LinkBtn .VideoBtn")

def extract_video_urls(driver, load_timeout=20, settle_wait=0.5):
    """
    Scrape video URLs from sections matching:
      virtual-wrap -> virtual-box -> img-box -> LinkBtn -> VideoBtn

    Returns: list[str] of URLs (unique, order preserved).
    """

    def slow_scroll():
        # Nudge lazy-loaders
        for y in (200, 800, 1600, 2400):
            driver.execute_script("window.scrollTo(0, arguments[0]);", y)
            time.sleep(0.2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.3)

    def safe_click(el):
        try:
            el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", el)

    def wait_all_video_buttons():
        """Wait until count of .VideoBtn stops increasing (or timeout)."""
        start = time.time()
        last = -1
        while time.time() - start < load_timeout:
            # Only in wraps that actually contain VideoBtn
            wraps = driver.find_elements(By.CSS_SELECTOR, ".virtual-wrap")
            btns = []
            for w in wraps:
                if w.find_elements(By.CSS_SELECTOR, ".img-box .LinkBtn .VideoBtn"):
                    try:
                        vb = w.find_element(By.CSS_SELECTOR, ".virtual-box")
                        btns.extend(vb.find_elements(By.CSS_SELECTOR, ".img-box .LinkBtn .VideoBtn"))
                    except Exception:
                        continue
            count = len(btns)
            if count > last:
                last = count
                slow_scroll()          # trigger more lazy-loads
                time.sleep(settle_wait)
            else:
                return btns            # stabilized
        return btns                    # timeout, return whatever we saw

    def try_popup_video_src():
        """Return src from popup <video> if a popup appears, else None."""
        try:
            WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, ".videoDIv, .videoDiv, .video-box"))
            )
            vid = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "video#video, video.videoDom, video"))
            )
            return (vid.get_attribute("src") or "").strip()
        except TimeoutException:
            return None
        finally:
            # try to close popup if it showed up
            try:
                close_btn = driver.find_element(By.CSS_SELECTOR, ".closeVideo")
                safe_click(close_btn)
                WebDriverWait(driver, 3).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, ".videoDIv, .videoDiv, .video-box"))
                )
            except Exception:
                pass

    def try_new_tab_url(main_handle):
        """Return URL from a newly opened tab, else None."""
        try:
            WebDriverWait(driver, 5).until(lambda d: len(d.window_handles) > 1)
            new_tab = [h for h in driver.window_handles if h != main_handle][0]
            driver.switch_to.window(new_tab)
            u = (driver.current_url or "").strip()
            return u
        except TimeoutException:
            return None
        finally:
            # close if we switched
            try:
                if driver.current_window_handle != main_handle:
                    driver.close()
                    driver.switch_to.window(main_handle)
            except Exception:
                try:
                    driver.switch_to.window(main_handle)
                except Exception:
                    pass

    def try_same_tab_url_change(prev_url):
        """If the click navigated the SAME tab, wait for URL change."""
        try:
            WebDriverWait(driver, 5).until(EC.url_changes(prev_url))
            return (driver.current_url or "").strip()
        except TimeoutException:
            return None

    # ---- main flow ----
    urls = []
    try:
        main = driver.current_window_handle

        # Ensure page is hydrated a bit before counting buttons
        time.sleep(1.0)
        slow_scroll()

        buttons = wait_all_video_buttons()
        if not buttons:
            print("[INFO] No video buttons found.")
            return []

        for btn in buttons:
            try:
                # Some sites require clicking the LinkBtn, not the span
                click_target = btn
                try:
                    click_target = btn.find_element(By.XPATH, "./ancestor::div[contains(@class,'LinkBtn')]")
                except Exception:
                    pass

                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", click_target)
                prev_url = driver.current_url
                safe_click(click_target)

                # 1) Try popup <video src>
                src = try_popup_video_src()
                if src:
                    urls.append(src)
                    continue

                # 2) Try new tab URL
                u = try_new_tab_url(main)
                if u:
                    urls.append(u)
                    continue

                # 3) Try same-tab navigation
                u2 = try_same_tab_url_change(prev_url)
                if u2:
                    urls.append(u2)
                    continue

            except StaleElementReferenceException:
                # tile re-rendered; skip this one
                continue
            except Exception as e:
                print(f"[INFO] Skipping a video tile due to error: {e}")
                continue

        # De-duplicate preserving order
        seen = set()
        urls = [u for u in urls if u and not (u in seen or seen.add(u))]

    except Exception as e:
        print(f"[INFO] Video extraction error: {e}")

    return urls


def extract_project_info(driver):
    data = {}
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
                    if label in TARGET_FIELDS:
                        data[label] = value
            except:
                continue
    except Exception as e:
        print(f"[ERROR] Failed to extract client-box: {e}")
    return data

def extract_description_content(driver):
    text_parts = []
    image_urls = []

    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".description-box .descriptionDiv"))
        )
        description_div = driver.find_element(By.CSS_SELECTOR, ".description-box .descriptionDiv")

        # Collect text
        for p in description_div.find_elements(By.TAG_NAME, "p"):
            t = p.text.strip()
            if t and t not in ["&nbsp;", "⚫"]:
                text_parts.append(t)

        # Collect ALL images (handle lazy-loading too)
        imgs = description_div.find_elements(By.TAG_NAME, "img")
        for img in imgs:
            src = (img.get_attribute("src") or "").strip()
            data_src = (img.get_attribute("data-src") or "").strip()
            u = src or data_src
            if u:
                # Make absolute in case the page uses relative paths
                u = urljoin(driver.current_url, u)
                image_urls.append(u)

        # de-dupe while preserving order
        seen = set()
        image_urls = [u for u in image_urls if not (u in seen or seen.add(u))]

    except Exception as e:
        print(f"[INFO] Description not found: {e}")

    return {
        "text": "\n\n".join(text_parts),
        "images": image_urls
    }

def extract_site_plan(driver):
    """Extracts the Site and Floor Plan section image URL."""
    title = "Site and Floor Plan"
    image_url = None
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "SiteFloorPlan")))
        site_plan_div = driver.find_element(By.ID, "SiteFloorPlan")

        _scroll_into_view(driver, site_plan_div)
        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#SiteFloorPlan img")))

        img = site_plan_div.find_element(By.TAG_NAME, "img")
        _wait_for_real_src(driver, img)

        src = (img.get_attribute("src") or "").strip()
        data_src = (img.get_attribute("data-src") or img.get_attribute("data-original") or "").strip()
        u = src or data_src
        if u:
            image_url = urljoin(driver.current_url, u)

    except Exception as e:
        print(f"[INFO] Site and Floor Plan section not found or image not loaded: {e}")

    return {"title": title, "image": image_url}


def extract_elevation_chart(driver):
    """Extracts the first image from the Elevation Chart section."""
    image_url = None
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "Elevation")))
        elevation_div = driver.find_element(By.ID, "Elevation")

        _scroll_into_view(driver, elevation_div)
        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#Elevation img")))

        img = elevation_div.find_element(By.TAG_NAME, "img")
        _wait_for_real_src(driver, img)

        src = (img.get_attribute("src") or "").strip()
        data_src = (img.get_attribute("data-src") or img.get_attribute("data-original") or "").strip()
        u = src or data_src
        if u:
            image_url = urljoin(driver.current_url, u)

    except Exception as e:
        print(f"[INFO] Elevation Chart section not found or image not loaded: {e}")

    return image_url

def extract_gallery_images(driver):
    """
    Get ALL image URLs from Gallery: .gallery-box > .img-box
    Robust for slow lazy-loading.
    """
    urls = []
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".gallery-box"))
        )
        gallery = driver.find_element(By.CSS_SELECTOR, ".gallery-box")
        img_box = gallery.find_element(By.CSS_SELECTOR, ".img-box")

        # start at left; bring into view
        driver.execute_script("arguments[0].scrollLeft = 0;", img_box)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", img_box)

        seen = set()
        last_seen_count = 0
        stagnant_passes = 0
        MAX_STAGNANT = 5           # allow more time before giving up
        SETTLE_SEC = 0.8           # time to let images load after each scroll
        MAX_PASSES = 60            # more passes for slow loading

        def collect_now():
            """Collect any newly rendered <img> urls from this img_box."""
            added = 0
            imgs = img_box.find_elements(By.TAG_NAME, "img")
            for img in imgs:
                # wait up to 3s for a real render
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", img)
                    WebDriverWait(driver, 3).until(
                        lambda d: d.execute_script("return arguments[0].naturalWidth > 0;", img)
                    )
                except:
                    pass
                src = (img.get_attribute("src") or "").strip()
                ds  = (img.get_attribute("data-src") or img.get_attribute("data-original") or "").strip()
                u = src or ds
                if not u or u.startswith("data:"):
                    continue
                u = urljoin(driver.current_url, u)
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
                    added += 1
            return added

        # initial wait for first images in view
        try:
            WebDriverWait(driver, 10).until(
                lambda d: len(img_box.find_elements(By.TAG_NAME, "img")) > 0
            )
        except:
            pass
        collect_now()

        for _ in range(MAX_PASSES):
            # give time for lazy loader to fire
            time.sleep(SETTLE_SEC)
            added = collect_now()

            if len(seen) == last_seen_count:
                stagnant_passes += 1
            else:
                stagnant_passes = 0
                last_seen_count = len(seen)

            if stagnant_passes >= MAX_STAGNANT:
                break

            # scroll one viewport right
            driver.execute_script("arguments[0].scrollLeft += arguments[0].clientWidth;", img_box)

            # stop if end reached
            sl, sw, cw = driver.execute_script(
                "return [arguments[0].scrollLeft, arguments[0].scrollWidth, arguments[0].clientWidth];", img_box
            )
            if sl + cw >= sw - 2:
                # linger at the end to catch stragglers
                for _ in range(3):
                    time.sleep(SETTLE_SEC)
                    collect_now()
                break

        print(f"[GALLERY] collected {len(urls)} urls")

    except Exception as e:
        print(f"[INFO] Gallery section not found or empty: {e}")

    return urls

def extract_virtual_tour_links(driver):
    urls = []
    try:
        wraps = driver.find_elements(By.CSS_SELECTOR, ".virtual-wrap")
        if not wraps:
            print("[INFO] No virtual-wrap found.")
            return []

        main_window = driver.current_window_handle

        for wrap in wraps:
            try:
                virtual_box = wrap.find_element(By.CSS_SELECTOR, ".virtual-box")
                img_boxes = virtual_box.find_elements(By.CSS_SELECTOR, ".img-box")
            except Exception:
                continue  # skip if structure missing

            # Check if this wrap contains Virtual Tour (iconSpn buttons)
            if not wrap.find_elements(By.CSS_SELECTOR, ".img-box .LinkBtn .iconSpn"):
                continue  # not a virtual tour section

            print("[DEBUG] Found Virtual Tour section")

            for img_box in img_boxes:
                try:
                    link_btn = img_box.find_element(By.CSS_SELECTOR, ".LinkBtn .iconSpn")
                except Exception:
                    continue

                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link_btn)
                link_btn.click()
                WebDriverWait(driver, 5).until(lambda d: len(d.window_handles) > 1)

                new_tab = [h for h in driver.window_handles if h != main_window][0]
                driver.switch_to.window(new_tab)

                tour_url = driver.current_url
                if tour_url:
                    urls.append(tour_url)

                driver.close()
                driver.switch_to.window(main_window)

        # de-duplicate
        seen = set()
        urls = [u for u in urls if u and not (u in seen or seen.add(u))]

    except Exception as e:
        print(f"[INFO] Virtual tour extraction error: {e}")

    return urls

def extract_floor_plan_images(driver):
    """
    Collect ALL floor plan images from: .floor-plans-box .plans-box img
    Handles lazy-loading by scrolling the plans container.
    """
    urls = []
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".floor-plans-box"))
        )
        box = driver.find_element(By.CSS_SELECTOR, ".floor-plans-box")
        plans = box.find_element(By.CSS_SELECTOR, ".plans-box")

        # bring into view
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", plans)
        time.sleep(0.3)

        seen = set()
        last_count = -1
        stagnant = 0

        # vertical scroll to force load
        for _ in range(40):
            imgs = plans.find_elements(By.TAG_NAME, "img")
            for img in imgs:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", img)
                    WebDriverWait(driver, 2).until(
                        lambda d: d.execute_script("return arguments[0].naturalWidth > 0;", img)
                    )
                except:
                    pass

                src = (img.get_attribute("src") or "").strip()
                data_src = (img.get_attribute("data-src") or img.get_attribute("data-original") or "").strip()
                u = src or data_src
                if u:
                    u = urljoin(driver.current_url, u)
                    if u not in seen:
                        seen.add(u)
                        urls.append(u)

            # stop if no new after a few passes
            if len(urls) == last_count:
                stagnant += 1
            else:
                stagnant = 0
                last_count = len(urls)
            if stagnant >= 3:
                break

            # scroll one viewport down inside the plans container (or page fallback)
            driver.execute_script("arguments[0].scrollTop += Math.max(400, arguments[0].clientHeight);", plans)
            time.sleep(0.3)

            # if container doesn't scroll, nudge the page
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(0.2)

    except Exception as e:
        print(f"[INFO] Floor plans section not found or empty: {e}")

    return urls


def upload_to_airtable(record, record_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}/{record_id}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    fields = {}
    # only include non-empty scalar fields from TARGET_FIELDS
    for key in TARGET_FIELDS:
        val = record.get(key)
        if isinstance(val, str):
            if val.strip():
                fields[key] = val.strip()
        elif val not in (None, "", []):
            fields[key] = val

    if record.get("Description", "").strip():
        fields["Description"] = record["Description"].strip()
        print("done 1")

    imgs = record.get("Description Images", [])
    if imgs:
        fields["Description Images"] = [{"url": u} for u in imgs]
        print("done 2")


    sp = record.get("SitePlanImage")
    if sp:
        fields["Site and Floor Plan"] = [{"url": sp}]
        print("done 3")


    ec = record.get("ElevationChartImage")
    if ec:
        fields["Elevation Chart"] = [{"url": ec}]
        print("done 4")


    gallery = record.get("GalleryImages", [])
    if gallery:
        fields["Gallery"] = [{"url": u} for u in gallery]
        print("done 5")


    vt_links = record.get("Virtual Tour Links", []) or record.get("VirtualTourURLS", [])
    if vt_links:
        fields["VirtualTourURLS"] = "\n".join(vt_links)
        print("done 6")


    fp_list = record.get("FloorPlanImages", [])
    if fp_list:
        fields["Floor Plan"] = [{"url": u} for u in fp_list]
        print("done 7")


    videos = record.get("Videos", [])
    if videos:
        fields["Videos"] = [
            {"url": v["url"]} if isinstance(v, dict) else {"url": v}
            for v in videos
        ]
        print("done 8")


    payload = {"fields": fields}
    response = requests.patch(url, headers=headers, json=payload, timeout=60)
    if response.status_code == 200:
        print(f"[UPDATED] Record {record_id} updated successfully.")
    else:
        print(f"[FAILED] Airtable update failed for {record_id}: {response.status_code}")
        print(response.text)




def run_scraper(URL, record_id):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=chrome_options)

    try:
        print(f"[INFO] Navigating to {URL}")
        driver.get(URL)
        time.sleep(30)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(20)

        record = {}
        project_info = extract_project_info(driver)
        description = extract_description_content(driver)
        site_plan = extract_site_plan(driver)
        elevation_chart_url = extract_elevation_chart(driver)
        gallery_urls = extract_gallery_images(driver)
        virtual_links = extract_virtual_tour_links(driver)
        floor_plan_urls = extract_floor_plan_images(driver)
        video_urls = extract_video_urls(driver)      
        asset_urls = filter_video_assets(video_urls) 

        record.update(project_info)
        record["Description"] = description["text"] or "No description available"
        record["Description Images"] = description["images"]
        record["Virtual Tour Links"] = virtual_links
        site_plan_url = site_plan["image"]  
        if site_plan_url:
            record["SitePlanImage"]  = site_plan_url  
            record["FloorPlanImage"] = site_plan_url
        
        if elevation_chart_url:
            record["ElevationChartImage"] = elevation_chart_url

        record["GalleryImages"] = gallery_urls
        record["FloorPlanImages"] = floor_plan_urls
        record["Videos"] = [{"url": u} for u in asset_urls]


        print("\n[DATA EXTRACTED]")
        print(json.dumps(record, indent=2))

        upload_to_airtable(record, record_id)

    finally:
        driver.quit()

def _scroll_into_view(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)

def _wait_for_real_src(driver, img, timeout=10):
    # wait until the <img> has a non-empty real src OR is rendered (naturalWidth > 0)
    WebDriverWait(driver, timeout).until(
        lambda d: (
            (img.get_attribute("src") and img.get_attribute("src").strip() and
             not img.get_attribute("src").strip().startswith("data:"))
            or d.execute_script("return arguments[0].naturalWidth > 0;", img)
        )
    )

def main():
    print("here 2")
    start_from = 0
    count = 0
    processed = 0

    for rec_id, listing_url in iter_listing_urls_from_airtable(limit=None):
        count += 1
        if count < start_from:
            continue

        try:
            print(f"\n▶️  Processing {count}: {listing_url} (Record ID: {rec_id})")
            run_scraper(listing_url, rec_id)
            processed += 1
            time.sleep(2.0)
            print("done 9")
        except Exception as e:
            print(f"[ERROR] while processing {listing_url}: {e}")

    print(f"\n✅ Scraper ran {processed} time(s), starting from record #{start_from}.")

if __name__ == "__main__":
    main()


# def extract_virtual_tour_links(driver):
#     urls = []
#     try:
#         # Find the first virtual-wrap only
#         wraps = driver.find_elements(By.CSS_SELECTOR, ".virtual-wrap")
#         if not wraps:
#             print("[INFO] No virtual-wrap found.")
#             return []

#         virtual_wrap = wraps[0]  # first one = Virtual Tour
#         link_buttons = virtual_wrap.find_elements(By.CSS_SELECTOR, ".LinkBtn")

#         main_window = driver.current_window_handle

#         for btn in link_buttons:
#             driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
#             btn.click()
#             WebDriverWait(driver, 5).until(lambda d: len(d.window_handles) > 1)

#             new_tab = [h for h in driver.window_handles if h != main_window][0]
#             driver.switch_to.window(new_tab)

#             tour_url = driver.current_url
#             if tour_url:
#                 urls.append(tour_url)

#             driver.close()
#             driver.switch_to.window(main_window)

#         # de-duplicate
#         seen = set()
#         urls = [u for u in urls if not (u in seen or seen.add(u))]

#     except Exception as e:
#         print(f"[INFO] Virtual tour section not found or error: {e}")

#     return urls


# if __name__ == "__main__":
#     start_from = 0  # 1-based counter in the prints; 0 means process from the first record
#     count = 0
#     processed = 0

#     for rec_id, listing_url in iter_listing_urls_from_airtable(limit=None):
#         count += 1
#         if count < start_from:
#             continue  # skip until we reach desired start index

#         try:
#             print(f"\n▶️  Processing #{count}: {listing_url} (Record ID: {rec_id})")

#             # 1) FIRST: scrape ALL info for this listing
#             run_scraper(listing_url, rec_id)
#             processed += 1
#             time.sleep(1.0)  # polite delay

#         except Exception as e:
#             print(f"[ERROR] while processing {listing_url}: {e}")

#     print(f"\n✅ Scraper ran {processed} time(s), starting from record #{start_from}.")

#works occasinlgy 1-many
# def extract_video_urls(driver):
#     urls = []
#     try:
#         wraps = driver.find_elements(By.CSS_SELECTOR, ".virtual-wrap")
#         if not wraps:
#             print("[INFO] No virtual-wrap found.")
#             return []

#         main = driver.current_window_handle

#         for wrap in wraps:
#             # Process ONLY wraps that contain Video buttons
#             if not wrap.find_elements(By.CSS_SELECTOR, ".img-box .LinkBtn .VideoBtn"):
#                 continue

#             # descend: virtual-wrap → .virtual-box → .img-box
#             try:
#                 virtual_box = wrap.find_element(By.CSS_SELECTOR, ".virtual-box")
#                 img_boxes = virtual_box.find_elements(By.CSS_SELECTOR, ".img-box")
#             except Exception:
#                 continue

#             for box in img_boxes:
#                 # skip boxes without a VideoBtn
#                 if not box.find_elements(By.CSS_SELECTOR, ".LinkBtn .VideoBtn"):
#                     continue

#                 # Prefer clicking the VideoBtn; fallback to the LinkBtn if needed
#                 try:
#                     click_el = box.find_element(By.CSS_SELECTOR, ".LinkBtn .VideoBtn")
#                 except Exception:
#                     try:
#                         click_el = box.find_element(By.CSS_SELECTOR, ".LinkBtn")
#                     except Exception:
#                         continue

#                 # Scroll into view and click
#                 driver.execute_script("arguments[0].scrollIntoView({block:'center'});", click_el)
#                 try:
#                     click_el.click()
#                 except Exception:
#                     # sometimes the span is not the clickable target; try the LinkBtn
#                     try:
#                         box.find_element(By.CSS_SELECTOR, ".LinkBtn").click()
#                     except Exception:
#                         continue

#                 # Case A: popup overlay with <video> element
#                 try:
#                     WebDriverWait(driver, 5).until(
#                         EC.visibility_of_element_located((By.CSS_SELECTOR, ".videoDIv, .videoDiv, .video-box"))
#                     )
#                     try:
#                         video_el = WebDriverWait(driver, 5).until(
#                             EC.presence_of_element_located((By.CSS_SELECTOR, "video#video, video.videoDom, video"))
#                         )
#                         src = (video_el.get_attribute("src") or "").strip()
#                         if src:
#                             urls.append(src)
#                     finally:
#                         # close popup if present
#                         try:
#                             close_btn = driver.find_element(By.CSS_SELECTOR, ".closeVideo")
#                             close_btn.click()
#                             WebDriverWait(driver, 3).until(
#                                 EC.invisibility_of_element_located((By.CSS_SELECTOR, ".videoDIv, .videoDiv, .video-box"))
#                             )
#                         except Exception:
#                             pass

#                 except TimeoutException:
#                     # Case B: new tab flow
#                     try:
#                         WebDriverWait(driver, 5).until(lambda d: len(d.window_handles) > 1)
#                         new_tab = [h for h in driver.window_handles if h != main][0]
#                         driver.switch_to.window(new_tab)
#                         u = (driver.current_url or "").strip()
#                         if u:
#                             urls.append(u)
#                     finally:
#                         try:
#                             if driver.current_window_handle != main:
#                                 driver.close()
#                                 driver.switch_to.window(main)
#                         except Exception:
#                             driver.switch_to.window(main)

#         # de-dupe while preserving order
#         seen = set()
#         urls = [u for u in urls if u and not (u in seen or seen.add(u))]

#     except Exception as e:
#         print(f"[INFO] Video extraction error: {e}")

#     return urls

# def extract_video_urls(driver):
#     urls = []
#     try:
#         # 1) Find all virtual-wraps and select the 2nd one (Video section)
#         wraps = driver.find_elements(By.CSS_SELECTOR, ".virtual-wrap")
#         if len(wraps) < 2:
#             print("[INFO] Video wrap not found.")
#             return []

#         video_wrap = wraps[1]  # Second virtual-wrap
#         print("[DEBUG] Found Video section.")

#         # 2) Find the virtual-box inside the video_wrap
#         try:
#             virtual_box = video_wrap.find_element(By.CSS_SELECTOR, ".virtual-box")
#         except Exception:
#             print("[INFO] virtual-box not found inside Video section.")
#             return []

#         # 3) Find all img-boxes inside virtual-box
#         img_boxes = virtual_box.find_elements(By.CSS_SELECTOR, ".img-box")
#         if not img_boxes:
#             print("[INFO] No img-box found inside virtual-box.")
#             return []

#         main = driver.current_window_handle

#         # 4) Loop over each img-box
#         for img_box in img_boxes:
#             try:
#                 # Find the LinkBtn inside img-box
#                 link_btn = img_box.find_element(By.CSS_SELECTOR, ".LinkBtn")

#                 # Find the VideoBtn inside LinkBtn
#                 video_btn = link_btn.find_element(By.CSS_SELECTOR, ".VideoBtn")

#                 # Scroll into view and click
#                 driver.execute_script("arguments[0].scrollIntoView({block:'center'});", video_btn)
#                 video_btn.click()

#                 # Case A: popup overlay with <video>
#                 try:
#                     WebDriverWait(driver, 5).until(
#                         EC.visibility_of_element_located((By.CSS_SELECTOR, ".videoDIv, .videoDiv, .video-box"))
#                     )
#                     try:
#                         video_el = WebDriverWait(driver, 5).until(
#                             EC.presence_of_element_located((By.CSS_SELECTOR, "video#video, video.videoDom, video"))
#                         )
#                         src = (video_el.get_attribute("src") or "").strip()
#                         if src:
#                             urls.append(src)
#                     finally:
#                         # Close popup if possible
#                         try:
#                             close_btn = driver.find_element(By.CSS_SELECTOR, ".closeVideo")
#                             close_btn.click()
#                             WebDriverWait(driver, 3).until(
#                                 EC.invisibility_of_element_located((By.CSS_SELECTOR, ".videoDIv, .videoDiv, .video-box"))
#                             )
#                         except Exception:
#                             pass

#                 except TimeoutException:
#                     # Case B: New tab opened
#                     try:
#                         WebDriverWait(driver, 5).until(lambda d: len(d.window_handles) > 1)
#                         new_tab = [h for h in driver.window_handles if h != main][0]
#                         driver.switch_to.window(new_tab)
#                         u = driver.current_url
#                         if u:
#                             urls.append(u)
#                     finally:
#                         try:
#                             if driver.current_window_handle != main:
#                                 driver.close()
#                                 driver.switch_to.window(main)
#                         except Exception:
#                             driver.switch_to.window(main)

#             except Exception as e:
#                 print(f"[INFO] Skipping img-box due to error: {e}")

#         # De-duplicate while preserving order
#         seen = set()
#         urls = [u for u in urls if u and not (u in seen or seen.add(u))]

#     except Exception as e:
#         print(f"[INFO] Video extraction error: {e}")

#     return urls

# def extract_video_urls(driver):
#     urls = []
#     try:
#         wraps = driver.find_elements(By.CSS_SELECTOR, ".virtual-wrap")
#         if len(wraps) < 2:
#             print("[INFO] Video wrap not found.")
#             return []

#         video_wrap = wraps[1]  # second .virtual-wrap = Video section
#         buttons = video_wrap.find_elements(By.CSS_SELECTOR, ".LinkBtn .VideoBtn")

#         main = driver.current_window_handle

#         for btn in buttons:
#             driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
#             btn.click()

#             # Case A: popup overlay with <video id="video">
#             try:
#                 WebDriverWait(driver, 5).until(
#                     EC.visibility_of_element_located((By.CSS_SELECTOR, ".videoDIv, .videoDiv, .video-box"))
#                 )
#                 try:
#                     video_el = WebDriverWait(driver, 5).until(
#                         EC.presence_of_element_located((By.CSS_SELECTOR, "video#video, video.videoDom, video"))
#                     )
#                     src = (video_el.get_attribute("src") or "").strip()
#                     if src:
#                         urls.append(src)
#                 finally:
#                     # close popup if close button exists
#                     try:
#                         close_btn = driver.find_element(By.CSS_SELECTOR, ".closeVideo")
#                         close_btn.click()
#                         WebDriverWait(driver, 3).until(
#                             EC.invisibility_of_element_located((By.CSS_SELECTOR, ".videoDIv, .videoDiv, .video-box"))
#                         )
#                     except Exception:
#                         pass

#             except TimeoutException:
#                 # Case B: new tab opened
#                 try:
#                     WebDriverWait(driver, 5).until(lambda d: len(d.window_handles) > 1)
#                     new_tab = [h for h in driver.window_handles if h != main][0]
#                     driver.switch_to.window(new_tab)
#                     u = driver.current_url
#                     if u:
#                         urls.append(u)
#                 finally:
#                     # close new tab if we switched
#                     try:
#                         if driver.current_window_handle != main:
#                             driver.close()
#                             driver.switch_to.window(main)
#                     except Exception:
#                         driver.switch_to.window(main)

#         # de-dupe while preserving order
#         seen = set()
#         urls = [u for u in urls if u and not (u in seen or seen.add(u))]

#     except Exception as e:
#         print(f"[INFO] Video extraction error: {e}")

#     return urls

