#!/usr/bin/env python3
"""
Behatsdaa Participating Stores Multi-Card Scraper
Discovers all cards from https://www.behatsdaa.org.il/card/chargingCard,
extracts participating stores and discounts per card, unifies them into
a deduplicated catalog, and outputs data/stores.json and data/stores.csv.
"""

import os
import sys
import json
import re
import csv
import time
import argparse
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, parse_qs, urlparse

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Optional Groq client
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def parse_arguments():
    parser = argparse.ArgumentParser(description="Scrape participating stores across all Behatsdaa cards.")
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Directory to save stores.json and stores.csv (default: 'data')"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run browser in headless mode (default: False, headful is more reliable against Incapsula)"
    )
    parser.add_argument(
        "--card-url",
        default="https://www.behatsdaa.org.il/card/chargingCard",
        help="Main cards page URL"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60000,
        help="Navigation timeout in milliseconds (default: 60000)"
    )
    return parser.parse_args()


def extract_discount_percent(text):
    """Extract numeric percentage from discount strings like '20%', 'עד 15% הנחה'"""
    if not text:
        return 0
    match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
    if match:
        try:
            return int(float(match.group(1)))
        except ValueError:
            pass
    # Fallback search for standalone numbers
    match = re.search(r'(\d+)', text)
    if match:
        val = int(match.group(1))
        if 1 <= val <= 100:
            return val
    return 0


def call_groq_enhancement(stores, categories):
    """
    Optional Groq LLM integration to clean up categories, standardize Hebrew terms,
    and resolve unclassified stores.
    """
    if not GROQ_API_KEY:
        return stores

    print(f"[*] GROQ_API_KEY detected. Running LLM enrichment with model {GROQ_MODEL}...")
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)

        prompt = f"""
אתה עוזר לסדר קטלוג חנויות של מועדון בהצדעה.
להלן רשימת קטגוריות תקניות:
- אופנה והנעלה
- מזון, מסעדות ובתי קפה
- בית, חשמל ועיצוב
- פארם, יופי ובריאות
- פנאי, תרבות וספורט
- ספרים ופנאי
- תיירות ונופש
- כללי

הנחיות:
1. התאם לכל רשת את הקטגוריה המתאימה ביותר מהרשימה התקנית בלבד.
2. נקה את שורת התנאים (אם קיימת) מתווים מיותרים.
3. החזר אך ורק מערך JSON תקני של אובייקטים עם השדות:
   "name", "category", "clean_conditions"

נתוני החנויות:
{json.dumps([{"name": s["name"], "category": s.get("category", ""), "conditions": s.get("conditions", "")} for s in stores[:40]], ensure_ascii=False)}
"""
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are a Hebrew data processing expert. Reply only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )

        resp_content = completion.choices[0].message.content
        data = json.loads(resp_content)
        enhancements = data.get("stores") or data.get("items") or (data if isinstance(data, list) else [])
        if isinstance(enhancements, list):
            lookup = {e.get("name"): e for e in enhancements if e.get("name")}
            for s in stores:
                if s["name"] in lookup:
                    e = lookup[s["name"]]
                    if e.get("category"):
                        s["category"] = e["category"]
                    if e.get("clean_conditions"):
                        s["conditions"] = e["clean_conditions"]
        print("[+] Groq enrichment completed successfully.")
    except Exception as e:
        print(f"[!] Groq enrichment encountered an error (continuing without LLM): {e}")

    return stores


def scrape_with_playwright(args):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n[ERROR] Playwright is not installed!")
        print("Run the following commands to install dependencies:")
        print("  pip install -r requirements.txt")
        print("  playwright install chromium\n")
        sys.exit(1)

    all_scraped_stores = {}
    discovered_cards = []
    intercepted_api_data = {}

    print("==========================================================")
    print("      בהצדעה - סורק רשתות מכבדות לכל סוגי הכרטיסים       ")
    print("==========================================================")
    print(f"[*] Main URL: {args.card_url}")
    print(f"[*] Headless: {args.headless}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--start-maximized"
            ]
        )

        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="he-IL",
            timezone_id="Asia/Jerusalem",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )

        page = context.new_page()

        # Listen to network responses to capture internal JSON APIs
        def handle_response(response):
            try:
                url = response.url
                if ("api" in url.lower() or "shops" in url.lower() or "wallet" in url.lower()) and "json" in response.headers.get("content-type", ""):
                    try:
                        data = response.json()
                        intercepted_api_data[url] = data
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", handle_response)

        # 1. Navigate to main Charging Cards page
        print(f"\n[1/3] Navigating to chargingCard page: {args.card_url}")
        try:
            page.goto(args.card_url, wait_until="networkidle", timeout=args.timeout)
        except Exception as e:
            print(f"[!] Warning on navigation: {e}")

        # Wait for content or Incapsula challenge resolution
        print("[*] Waiting for cards content to load...")
        time.sleep(4)

        # Extract all card links / wallets
        # Look for buttons/links containing 'shops', 'walletId', or text matching 'רשתות מכבדות'
        card_links = page.locator("a[href*='walletId'], a[href*='shops'], button:has-text('רשתות'), a:has-text('רשתות')").all()
        print(f"[*] Located {len(card_links)} candidate shop links/buttons.")

        card_targets = []
        for link in card_links:
            try:
                href = link.get_attribute("href") or ""
                text = link.inner_text().strip()
                parent_text = link.locator("xpath=../..").inner_text().strip()
                
                # Extract card name from parent container or link
                lines = [l.strip() for l in parent_text.split("\n") if l.strip()]
                card_name = lines[0] if lines else "כרטיס בהצדעה"

                if "walletId=" in href:
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    wallet_id = qs.get("walletId", [None])[0]
                    if wallet_id:
                        card_targets.append({
                            "card_name": card_name,
                            "wallet_id": wallet_id,
                            "url": urljoin(args.card_url, href)
                        })
            except Exception:
                continue

        # If no direct links found, inspect page links and wallet query parameters
        if not card_targets:
            print("[*] Checking page source for wallet IDs...")
            content = page.content()
            wallet_matches = re.findall(r'walletId[=:]\s*["\']?(\d+)["\']?', content)
            unique_wallets = list(dict.fromkeys(wallet_matches))
            for wid in unique_wallets:
                card_targets.append({
                    "card_name": f"כרטיס בהצדעה (ארנק {wid})",
                    "wallet_id": wid,
                    "url": f"https://www.behatsdaa.org.il/card/shops?walletId={wid}"
                })

        # Ensure at least wallet 3379 (user mentioned) is present
        wallet_ids = [c["wallet_id"] for c in card_targets]
        if "3379" not in wallet_ids:
            card_targets.append({
                "card_name": "כרטיס בהצדעה נטען (ראשי)",
                "wallet_id": "3379",
                "url": "https://www.behatsdaa.org.il/card/shops?walletId=3379"
            })

        print(f"[+] Found {len(card_targets)} card targets to scrape:")
        for idx, ct in enumerate(card_targets, 1):
            print(f"    {idx}. {ct['card_name']} (walletId: {ct['wallet_id']})")
            discovered_cards.append({
                "id": f"card-{ct['wallet_id']}",
                "name": ct["card_name"],
                "wallet_id": ct["wallet_id"],
                "url": ct["url"]
            })

        # 2. Iterate each card and scrape its participating stores
        print("\n[2/3] Scraping participating stores for each card...")
        for ct in card_targets:
            card_id = f"card-{ct['wallet_id']}"
            card_name = ct["card_name"]
            card_url = ct["url"]

            print(f"\n[*] Loading stores for: {card_name} -> {card_url}")
            try:
                page.goto(card_url, wait_until="networkidle", timeout=args.timeout)
                time.sleep(3)
            except Exception as err:
                print(f"[!] Error loading {card_url}: {err}")
                continue

            # Check if internal API provided data for this wallet
            stores_found = []
            for url, json_data in intercepted_api_data.items():
                if ct["wallet_id"] in url or "shops" in url or "stores" in url:
                    items = []
                    if isinstance(json_data, list):
                        items = json_data
                    elif isinstance(json_data, dict):
                        for k in ["data", "shops", "stores", "items", "result"]:
                            if k in json_data and isinstance(json_data[k], list):
                                items = json_data[k]
                                break
                    if items:
                        for itm in items:
                            if isinstance(itm, dict):
                                name = itm.get("name") or itm.get("shopName") or itm.get("title")
                                if name:
                                    stores_found.append({
                                        "name": name.strip(),
                                        "category": itm.get("category") or itm.get("categoryName") or "כללי",
                                        "logo": itm.get("logo") or itm.get("logoUrl") or itm.get("imageUrl") or "",
                                        "discount": itm.get("discount") or itm.get("discountPercent") or "הנחת מועדון",
                                        "conditions": itm.get("conditions") or itm.get("notes") or "",
                                        "website": itm.get("website") or itm.get("url") or ""
                                    })
                        if stores_found:
                            print(f"[+] Extracted {len(stores_found)} stores from API response!")
                            break

            # If API did not yield stores, parse DOM elements
            if not stores_found:
                print("[*] Parsing store cards from DOM...")
                # Scroll down to trigger lazy loading
                for _ in range(5):
                    page.mouse.wheel(0, 1000)
                    time.sleep(0.5)

                # Look for store elements / tiles
                store_selectors = [
                    ".shop-card", ".store-item", ".shop-item", "[class*='shop']", "[class*='store']",
                    ".card", "div.col-12", "div.col-md-4", "div.col-sm-6"
                ]
                
                dom_elements = []
                for sel in store_selectors:
                    els = page.locator(sel).all()
                    if len(els) >= 3:
                        dom_elements = els
                        break

                for el in dom_elements:
                    try:
                        text = el.inner_text().strip()
                        if not text or len(text) < 3:
                            continue
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        if not lines:
                            continue
                        
                        store_name = lines[0]
                        category = "כללי"
                        discount = "הנחה"
                        notes = ""

                        # Extract discount percentage if present
                        for l in lines:
                            if "%" in l or "הנחה" in l:
                                discount = l
                            if any(cat_word in l for cat_word in ["אופנה", "מזון", "מסעדות", "בית", "פארם", "ספרים", "ספורט", "נופש"]):
                                category = l

                        # Extract image/logo if available
                        img_el = el.locator("img").first
                        logo_url = ""
                        try:
                            if img_el.count() > 0:
                                logo_url = img_el.get_attribute("src") or ""
                        except Exception:
                            pass

                        stores_found.append({
                            "name": store_name,
                            "category": category,
                            "logo": logo_url,
                            "discount": discount,
                            "conditions": notes,
                            "website": ""
                        })
                    except Exception:
                        continue

            print(f"[+] Total stores extracted for '{card_name}': {len(stores_found)}")

            # Merge stores into unified map
            for s in stores_found:
                sname = s["name"]
                if sname not in all_scraped_stores:
                    all_scraped_stores[sname] = {
                        "id": re.sub(r'[^a-zA-Z0-9\u0590-\u05FF]+', '-', sname).strip('-').lower() or f"store-{len(all_scraped_stores)+1}",
                        "name": sname,
                        "category": s.get("category") or "כללי",
                        "logo": s.get("logo", ""),
                        "website": s.get("website", ""),
                        "conditions": s.get("conditions", ""),
                        "cards": [],
                        "max_discount": 0
                    }

                # Add card membership
                disc_num = extract_discount_percent(s.get("discount", ""))
                all_scraped_stores[sname]["cards"].append({
                    "card_id": card_id,
                    "card_name": card_name,
                    "discount": s.get("discount") or f"{disc_num}%" if disc_num else "הנחת מועדון",
                    "discount_numeric": disc_num,
                    "notes": s.get("conditions", "")
                })

                if disc_num > all_scraped_stores[sname]["max_discount"]:
                    all_scraped_stores[sname]["max_discount"] = disc_num

        browser.close()

    # Convert dictionary to list
    final_stores_list = list(all_scraped_stores.values())
    print(f"\n[+] Total unique stores across all cards: {len(final_stores_list)}")

    # If scrape extracted 0 stores (e.g. WAF block during automated run), fall back to existing data
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "stores.json"
    csv_path = output_dir / "stores.csv"

    if not final_stores_list:
        print("[!] No stores could be parsed from live session (possible WAF block or page structure change).")
        if json_path.exists():
            print(f"[*] Preserving existing {json_path} without overwriting.")
            return
        else:
            print("[!] Generating template data for testing.")
            return

    # 3. Groq LLM Enhancement (Optional)
    final_stores_list = call_groq_enhancement(final_stores_list, [])

    # Extract all distinct categories
    all_categories = sorted(list({s.get("category", "כללי") for s in final_stores_list if s.get("category")}))
    if "הכל" not in all_categories:
        all_categories.insert(0, "הכל")

    # Build output payload
    output_payload = {
        "metadata": {
            "title": "רשימת רשתות מכבדות - כרטיסי בהצדעה",
            "source": args.card_url,
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "total_stores": len(final_stores_list),
            "available_cards": discovered_cards,
            "categories": all_categories
        },
        "stores": final_stores_list
    }

    # Save data/stores.json
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False, indent=2)
    print(f"[+] Saved JSON catalog to: {json_path}")

    # Save data/stores.csv
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "שם הרשת / העסק",
            "קטגוריה",
            "כרטיסים תומכים",
            "הנחה מרבית %",
            "פירוט הנחות לפי כרטיס",
            "אתר אינטרנט",
            "תנאים והגבלות"
        ])
        for s in final_stores_list:
            card_names = ", ".join([c["card_name"] for c in s.get("cards", [])])
            breakdown = " | ".join([f"{c['card_name']}: {c['discount']}" for c in s.get("cards", [])])
            writer.writerow([
                s.get("name", ""),
                s.get("category", ""),
                card_names,
                s.get("max_discount", 0),
                breakdown,
                s.get("website", ""),
                s.get("conditions", "")
            ])
    print(f"[+] Saved CSV catalog to: {csv_path}")
    print("\n[SUCCESS] Scraping and catalog export finished successfully!")


def main():
    args = parse_arguments()
    scrape_with_playwright(args)


if __name__ == "__main__":
    main()

