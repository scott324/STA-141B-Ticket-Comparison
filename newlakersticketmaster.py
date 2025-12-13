import time
import re
from datetime import datetime

import requests
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


API_KEY = None #Insert your own API key here

# Lakers attraction ID on Ticketmaster (team as "attraction")
ATTRACTION_ID = "K8vZ91718T0"


START_DATETIME = "2025-12-01T00:00:00Z"
END_DATETIME   = "2026-06-30T23:59:59Z"
COUNTRY_CODE = "US"
OUTPUT_CSV = "lakers_remaining_games_with_min_price.csv"
HEADLESS = True

def fetch_lakers_events():
    base_url = "https://app.ticketmaster.com/discovery/v2/events.json"

    all_events = []
    page = 0
    page_size = 200

    while True:
        params = {
            "apikey": API_KEY,
            "attractionId": ATTRACTION_ID,
            "countryCode": COUNTRY_CODE,
            "startDateTime": START_DATETIME,
            "endDateTime": END_DATETIME,
            "size": page_size,
            "page": page,
            "sort": "date,asc",
            "locale": "*",
        }

        print(f"Requesting API page {page}...")
        resp = requests.get(base_url, params=params)
        try:
            resp.raise_for_status()
        except Exception as e:
            print("Error talking to Ticketmaster API:", e)
            print("Response text:", resp.text)
            break

        data = resp.json()
        embedded = data.get("_embedded", {})
        events = embedded.get("events", [])

        if not events:
            break

        all_events.extend(events)

        page_info = data.get("page", {})
        total_pages = page_info.get("totalPages", 1)

        if page >= total_pages - 1:
            break

        page += 1
        time.sleep(0.3)

    print(f"Fetched {len(all_events)} events from Ticketmaster.")

    rows = []

    for e in all_events:
        event_id = e.get("id")
        name = e.get("name")
        url = e.get("url")

        dates = e.get("dates", {})
        start = dates.get("start", {}) if isinstance(dates, dict) else {}
        utc_dt = start.get("dateTime")
        local_date = start.get("localDate")
        local_time = start.get("localTime")

        # take first venue
        venues = e.get("_embedded", {}).get("venues", [{}])
        venue = venues[0] if venues else {}
        venue_name = venue.get("name")
        city = venue.get("city", {}).get("name")
        state = venue.get("state", {}).get("stateCode") or venue.get("state", {}).get("name")
        country = venue.get("country", {}).get("countryCode") or venue.get("country", {}).get("name")

        # API price range (if they provide it)
        price_ranges = e.get("priceRanges") or []
        if price_ranges:
            pr = price_ranges[0]
            api_min_price = pr.get("min")
            api_max_price = pr.get("max")
            currency = pr.get("currency")
        else:
            api_min_price = None
            api_max_price = None
            currency = None

        rows.append(
            {
                "event_id": event_id,
                "event_name": name,
                "url": url,

                "start_datetime_utc": utc_dt,
                "start_date_local": local_date,
                "start_time_local": local_time,

                "venue_name": venue_name,
                "city": city,
                "state": state,
                "country": country,

                "api_min_price": api_min_price,
                "api_max_price": api_max_price,
                "currency": currency,

                # to be filled by Selenium scraper
                "scraped_min_price": None,
            }
        )

    df = pd.DataFrame(rows)

    if not df.empty and "start_datetime_utc" in df.columns:
        df["start_datetime_parsed"] = pd.to_datetime(df["start_datetime_utc"], errors="coerce")
        df = df.sort_values("start_datetime_parsed")

    return df.reset_index(drop=True)



def create_webdriver(headless=HEADLESS):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")  # if issues, change to "--headless"
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,900")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def scrape_min_price_from_page(url, driver, timeout=25):
    print(f"\nScraping min price from: {url}")
    try:
        driver.get(url)
    except Exception as e:
        print("  Error loading page:", e)
        return None

    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except Exception as e:
        print("  Timeout waiting for body:", e)
        return None

    # Try to close generic cookie/consent popups (best-effort)
    for text in ["Accept", "Agree", "Got it", "I Agree", "Accept All"]:
        try:
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[contains(., '{text}')]"))
            )
            btn.click()
            print(f"  Clicked cookie/consent button: {text}")
            break
        except Exception:
            pass

    try:
        slider_min_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[@data-bdd='exposed-mobile-filter-price-slider-min']")
            )
        )

        min_input = slider_min_container.find_element(By.XPATH, ".//input")

        raw_value = min_input.get_attribute("value") or ""

        if not raw_value:
            raw_value = min_input.get_attribute("aria-label") or ""

        print(f"  Raw slider min input value: {raw_value!r}")

        match = re.search(r"\$?\s*([0-9]+(?:\.[0-9]{1,2})?)", raw_value)
        if match:
            min_price = float(match.group(1))
            print(f"  [Slider min] Parsed minimum price: {min_price}")
            return min_price
        else:
            print("  [Slider min] Couldn't parse a number out of the input text.")

    except Exception as e:
        print("  [Slider min] Could not find or parse slider min input:", e)

    # 2) FALLBACK: scan entire page for any dollar amounts
    try:
        elements = driver.find_elements(By.XPATH, "//*[contains(text(), '$')]")
        texts = [el.text for el in elements if el.text]

        fallback_prices = []

        for txt in texts:
            for match in re.findall(r"\$?\s*([0-9]+(?:\.[0-9]{1,2})?)", txt):
                try:
                    val = float(match)
                    if val > 0:
                        fallback_prices.append(val)
                except ValueError:
                    pass

        if fallback_prices:
            min_price = min(fallback_prices)
            print(f"  [Fallback] Found min price: {min_price}")
            return min_price
        else:
            print("  [Fallback] No dollar amounts found anywhere.")
            return None

    except Exception as e:
        print("  Error in fallback price parsing:", e)
        return None


# Full pipeline

def build_lakers_min_price_table():
    df = fetch_lakers_events()
    if df.empty:
        print("No Lakers events found. Check API key, dates, or attraction ID.")
        return df

    print(f"\nGot {len(df)} events from Ticketmaster. Starting Selenium scraping...\n")

    driver = create_webdriver(headless=HEADLESS)

    try:
        for idx, row in df.iterrows():
            url = row.get("url")
            if not url:
                print(f"Row {idx}: no URL, skipping.")
                continue

            print(f"Event {idx + 1}/{len(df)}: {row.get('event_name')}")
            min_price = scrape_min_price_from_page(url, driver)
            df.at[idx, "scraped_min_price"] = min_price

            time.sleep(3)

    finally:
        driver.quit()

    cols_order = [
        "event_id",
        "event_name",
        "start_date_local",
        "start_time_local",
        "venue_name",
        "city",
        "state",
        "country",
        "url",
        "api_min_price",
        "api_max_price",
        "currency",
        "scraped_min_price",
    ]
    cols_order = [c for c in cols_order if c in df.columns]
    df = df[cols_order]

    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved {len(df)} events with scraped prices to {OUTPUT_CSV}")

    return df



# Run script

if __name__ == "__main__":
    print("Starting Lakers Ticketmaster min price scraper...")
    start_time = datetime.now()
    df_result = build_lakers_min_price_table()
    end_time = datetime.now()
    print("\nDone. Runtime:", end_time - start_time)







