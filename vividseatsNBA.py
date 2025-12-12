import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import re

#converting price from string to in
def convert_price(s):
    #Check if no price is listed
    if not s or "From" not in s:
        return np.nan
    #The prices are listed with "from" and a dollar sign, so to format as an int, these must be removed
    cleaned = s.replace("From", "").replace("$", "").strip()
    cleaned = cleaned.replace(",", "")
    try:
        return int(cleaned)
    except:
        return np.nan

#Generalized function to accept any team name and return info on all of events on vivid seats for that team
def scrape_vivid_performer(url, team_name):
    headers = {
        "User-Agent": None #Insert your user agent here
    }

    resp = requests.get(url, headers=headers)
    #Print the status of the request
    print(f"{team_name}: Status code", resp.status_code)

    soup = BeautifulSoup(resp.text, "html.parser")

    event_cards = soup.select('div[data-testid^="production-listing-"]')
    #Print the number of events found in the request results
    print(f"{team_name}: Found event cards:", len(event_cards))

    #Will hold the information from each event as a list of dictionaries
    rows = []

    for card in event_cards:
        #For each event, record the title, date, time, venue, and city by locating them in the text
        title_el = card.select_one(
            ".MuiTypography-root.MuiTypography-small-medium.styles_titleTruncate__XiZ53.mui-pc7loe"
        )
        date_el = card.select_one(
            ".MuiTypography-root.MuiTypography-small-bold.MuiTypography-noWrap.mui-1fmntk1"
        )
        time_el = card.select_one(
            ".MuiTypography-root.MuiTypography-caption.mui-1pgnteb"
        )
        venue_el = card.select_one(
            ".MuiTypography-root.MuiTypography-small-regular.styles_textTruncate__wsM3Q.mui-1insuh9"
        )
        city_el = card.select_one(
            ".MuiTypography-root.MuiTypography-small-regular.styles_textTruncate__wsM3Q.mui-1wl3fj7"
        )

        #The price is recorded, and then converted to an int to be stored separately
        price_el = card.find("span", string=lambda t: t and "From" in t)
        price_text = price_el.get_text(strip=True) if price_el else ""
        price_int = convert_price(price_text)

        #Find the event url
        link_el = card.find(
            "a",
            attrs={"data-testid": re.compile(r"production-listing-row-")}
        )

        #Record the event url
        if link_el and link_el.get("href"):
            href = link_el["href"]
            if href.startswith("/"):
                full_url = "https://www.vividseats.com" + href
            else:
                full_url = href
        else:
            full_url = url

        #Create a dictionary from the gathered data and add it on to everything already gathered
        rows.append({
            "platform":   "VividSeats",
            "team":       team_name,
            "event_title": title_el.get_text(strip=True) if title_el else "",
            "event_date":  date_el.get_text(strip=True) if date_el else "",
            "event_time":  time_el.get_text(strip=True) if time_el else "",
            "venue":       venue_el.get_text(strip=True) if venue_el else "",
            "city":        city_el.get_text(strip=True) if city_el else "",
            "price_text":  price_text,
            "price_int":   price_int,
            "url":         full_url,
        })

    return rows

#Go through months so all the results fit on one page
month_urls = {
    "https://www.vividseats.com/los-angeles-lakers-tickets--sports-nba-basketball/performer/483?startDate=2025-12-10&endDate=2026-01-31",
    "https://www.vividseats.com/los-angeles-lakers-tickets--sports-nba-basketball/performer/483?startDate=2026-02-01&endDate=2026-02-28",
    "https://www.vividseats.com/los-angeles-lakers-tickets--sports-nba-basketball/performer/483?startDate=2026-03-01&endDate=2026-03-31",
    "https://www.vividseats.com/los-angeles-lakers-tickets--sports-nba-basketball/performer/483?startDate=2026-03-01&endDate=2026-03-31"
}

all_rows = []

for team, url in team_urls.items():
    rows = scrape_vivid_performer(url, "Lakers")
    all_rows.extend(rows)

df = pd.DataFrame(all_rows)
print(df.head())
df.to_csv("vividseats_nba.csv", index=False)
print("Saved vividseats_nba.csv")
