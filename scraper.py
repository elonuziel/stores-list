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

# Ensure UTF-8 stdout encoding on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

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
        help="Run browser in headless mode (default: False, headful required for login & WAF)"
    )
    parser.add_argument(
        "--card-url",
        default="https://www.behatsdaa.org.il/card/chargingCard",
        help="Main cards page URL"
    )
    parser.add_argument(
        "--browser", "--channel",
        dest="browser",
        choices=["chrome", "msedge", "edge", "chromium"],
        default="chrome",
        help="Browser to use: 'chrome' (Google Chrome, default), 'edge' / 'msedge' (Microsoft Edge), or 'chromium'"
    )
    parser.add_argument(
        "--cdp",
        default=None,
        help="Connect to an already open browser via Chrome DevTools Protocol port or URL (e.g. 9222 or http://localhost:9222)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60000,
        help="Navigation timeout in milliseconds (default: 60000)"
    )
    parser.add_argument(
        "--profile-dir",
        default="./behatsdaa_profile",
        help="Directory to store persistent browser profile and login session (default: ./behatsdaa_profile)"
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
    match = re.search(r'(\d+)', text)
    if match:
        val = int(match.group(1))
        if 1 <= val <= 100:
            return val
    return 0


def call_groq_enhancement(stores):
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


def launch_stealth_context(p, profile_dir, headless=False, channel=None):
    """
    Launch persistent Chromium context with stealth flags to bypass Incapsula WAF.
    Persists cookies and login session so user only has to log in once.
    """
    profile_path = Path(profile_dir).resolve()
    profile_path.mkdir(parents=True, exist_ok=True)

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-infobars"
    ]
    channels = [channel] if channel else ["chrome", "msedge", None]

    for ch in channels:
        try:
            kwargs = {
                "user_data_dir": str(profile_path),
                "headless": headless,
                "args": launch_args,
                "ignore_default_args": ["--enable-automation"],
                "locale": "he-IL",
                "timezone_id": "Asia/Jerusalem",
                "viewport": {"width": 1400, "height": 900}
            }
            if ch:
                kwargs["channel"] = ch
                print(f"[*] Launching persistent browser using channel '{ch}'...")
            else:
                print("[*] Launching persistent browser using bundled Chromium...")

            context = p.chromium.launch_persistent_context(**kwargs)
            return context
        except Exception as e:
            msg = str(e).split('\n')[0]
            if ch:
                print(f"[*] Channel '{ch}' not available ({msg}), trying next option...")
            else:
                print(f"[!] Bundled Chromium launch failed: {msg}")

    raise RuntimeError(
        "Could not launch any browser! Please run:\n"
        "    playwright install chromium\n"
        "or ensure Google Chrome / Microsoft Edge is installed."
    )


def wait_for_user_login(page):
    """Detect if page redirected to /login and wait for user authentication."""
    if "/login" in page.url:
        print("\n" + "=" * 65)
        print(" [!] ACTION REQUIRED: Behatsdaa Login Needed")
        print("=" * 65)
        print(" Behatsdaa requires logging in to access cards and participating stores.")
        print(" -> Please log in (ID + SMS code) in the opened Chrome window.")
        print(" -> The scraper will automatically resume once you are logged in.")
        print("=" * 65 + "\n")

        try:
            # Wait up to 3 minutes for user to complete login
            page.wait_for_url(lambda u: "/login" not in u, timeout=180000)
            print("[+] Login detected successfully! Resuming scrape...")
        except Exception:
            print("[!] Timed out waiting for login. Proceeding with current page...")


def extract_stores_from_view(target, intercepted_api_data, wallet_id=None):
    """Extract stores from intercepted network JSON APIs or from DOM elements."""
    stores_found = []

    # 1. Try intercepted API responses
    for url, json_data in list(intercepted_api_data.items()):
        if (wallet_id and wallet_id in url) or "shops" in url.lower() or "stores" in url.lower() or "wallet" in url.lower():
            items = []
            if isinstance(json_data, list):
                items = json_data
            elif isinstance(json_data, dict):
                for k in ["data", "shops", "stores", "items", "result", "rows"]:
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
                                "discount": str(itm.get("discount") or itm.get("discountPercent") or "הנחת מועדון"),
                                "conditions": itm.get("conditions") or itm.get("notes") or "",
                                "website": itm.get("website") or itm.get("url") or ""
                            })
                if stores_found:
                    return stores_found

    # 2. Extract from DOM elements
    try:
        if hasattr(target, "mouse"):
            for _ in range(6):
                target.mouse.wheel(0, 1000)
                time.sleep(0.3)
    except Exception:
        pass

    dom_elements = target.locator("div[class*='shop'], div[class*='store'], div[class*='card'], .shop-item, .store-item").all()
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

            for l in lines:
                if "%" in l or "הנחה" in l:
                    discount = l
                if any(cat_word in l for cat_word in ["אופנה", "מזון", "מסעדות", "בית", "פארם", "ספרים", "ספורט", "נופש", "חשמל"]):
                    category = l

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

    return stores_found


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
    print("      Behatsdaa - Multi-Card Stores Scraper               ")
    print("==========================================================")
    print(f"[*] Target URL: {args.card_url}")
    print(f"[*] Headless: {args.headless}")
    if args.cdp:
        print(f"[*] Mode: Connect to existing open browser (CDP: {args.cdp})")
    else:
        print(f"[*] Browser: {args.browser}")
        print(f"[*] Profile Directory: {args.profile_dir}")

    with sync_playwright() as p:
        if args.cdp:
            endpoint = args.cdp if str(args.cdp).startswith("http") else f"http://localhost:{args.cdp}"
            print(f"[*] Connecting to your existing open browser over CDP: {endpoint} ...")
            browser = p.chromium.connect_over_cdp(endpoint)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
        else:
            browser_channel = args.browser.lower()
            if browser_channel in ["edge", "msedge"]:
                browser_channel = "msedge"
            elif browser_channel == "chromium":
                browser_channel = None
            else:
                browser_channel = "chrome"

            context = launch_stealth_context(
                p,
                profile_dir=args.profile_dir,
                headless=args.headless,
                channel=browser_channel
            )

        page = context.pages[0] if context.pages else context.new_page()

        # Hide webdriver flag
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        # Intercept store/card JSON responses
        def handle_response(response):
            try:
                url = response.url
                if ("api" in url.lower() or "shops" in url.lower() or "wallet" in url.lower() or "card" in url.lower()) and "json" in response.headers.get("content-type", ""):
                    try:
                        data = response.json()
                        intercepted_api_data[url] = data
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", handle_response)

        # 1. Navigate to main chargingCard page
        print(f"\n[1/3] Navigating to: {args.card_url}")
        try:
            page.goto(args.card_url, wait_until="networkidle", timeout=args.timeout)
        except Exception as e:
            print(f"[*] Navigation note: {e}")

        # Check for login requirement
        wait_for_user_login(page)

        time.sleep(3)

        # Extract all card links / wallets
        card_links = page.locator("a[href*='walletId'], a[href*='shops'], button:has-text('רשתות'), a:has-text('רשתות')").all()
        print(f"[*] Located {len(card_links)} candidate shop buttons/links on cards page.")

        card_targets = []
        for link in card_links:
            try:
                href = link.get_attribute("href") or ""
                parent_text = link.locator("xpath=../..").inner_text().strip()
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

        # Check page HTML for wallet IDs if no links matched
        if not card_targets:
            content = page.content()
            wallet_matches = re.findall(r'walletId[=:]\s*["\']?(\d+)["\']?', content)
            unique_wallets = list(dict.fromkeys(wallet_matches))
            for wid in unique_wallets:
                card_targets.append({
                    "card_name": f"כרטיס בהצדעה (ארנק {wid})",
                    "wallet_id": wid,
                    "url": f"https://www.behatsdaa.org.il/card/shops?walletId={wid}"
                })

        # Ensure default wallet 3379 is included
        wallet_ids = [c["wallet_id"] for c in card_targets]
        if "3379" not in wallet_ids:
            card_targets.append({
                "card_name": "כרטיס בהצדעה נטען (ראשי)",
                "wallet_id": "3379",
                "url": "https://www.behatsdaa.org.il/card/shops?walletId=3379"
            })

        print(f"[+] Found {len(card_targets)} card target(s) to scrape:")
        for idx, ct in enumerate(card_targets, 1):
            print(f"    {idx}. {ct['card_name']} (walletId: {ct['wallet_id']})")
            discovered_cards.append({
                "id": f"card-{ct['wallet_id']}",
                "name": ct["card_name"],
                "wallet_id": ct["wallet_id"],
                "url": ct["url"]
            })

        # 2. Scrape stores for each card
        print(f"\n[2/3] Scraping participating stores for each card...")
        for idx, ct in enumerate(card_targets, 1):
            card_id = f"card-{ct['wallet_id']}"
            card_name = ct["card_name"]
            card_url = ct["url"]

            print(f"\n[*] [{idx}/{len(card_targets)}] Loading stores for: {card_name} (walletId: {ct['wallet_id']})")

            # Try clicking the "Participating Stores" button on the cards page
            clicked = False
            if "chargingCard" in page.url:
                try:
                    btn = page.locator(f"a[href*='walletId={ct['wallet_id']}'], button:has-text('רשתות'), a:has-text('רשתות'), button:has-text('מכבדות'), a:has-text('מכבדות')").first
                    if btn.count() > 0 and btn.is_visible():
                        print(f"[*] Clicking 'Participating Stores' button for {card_name}...")
                        btn.scroll_into_view_if_needed()
                        time.sleep(0.5)
                        btn.click()
                        time.sleep(3)
                        clicked = True
                except Exception as e:
                    print(f"[*] Note on button click: {e}")

            # If not navigated by click, navigate directly to card_url
            if not clicked or "shops" not in page.url:
                try:
                    page.goto(card_url, wait_until="networkidle", timeout=args.timeout)
                except Exception as err:
                    print(f"[*] Navigation note: {err}")

            # Check if login is required
            wait_for_user_login(page)
            time.sleep(3)

            stores_found = extract_stores_from_view(page, intercepted_api_data, wallet_id=ct['wallet_id'])
            print(f"[+] Extracted {len(stores_found)} stores for '{card_name}'.")

            # Return to chargingCard if needed for next card
            if idx < len(card_targets) and "chargingCard" not in page.url:
                try:
                    page.goto(args.card_url, wait_until="networkidle", timeout=args.timeout)
                    time.sleep(2)
                except Exception:
                    pass

            # Merge into unified catalog
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

        context.close()

    final_stores_list = list(all_scraped_stores.values())
    print(f"\n[+] Total unique stores scraped across all cards: {len(final_stores_list)}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "stores.json"
    csv_path = output_dir / "stores.csv"

    if not final_stores_list:
        print("[!] No stores could be extracted during live session.")
        if json_path.exists():
            print(f"[*] Preserving existing {json_path} without overwriting.")
        return

    # 3. Optional Groq Enhancement
    final_stores_list = call_groq_enhancement(final_stores_list)

    all_categories = sorted(list({s.get("category", "כללי") for s in final_stores_list if s.get("category")}))
    if "הכל" not in all_categories:
        all_categories.insert(0, "הכל")

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

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False, indent=2)
    print(f"[+] Saved JSON catalog to: {json_path}")

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
    print("\n[SUCCESS] Scraping completed successfully!")


def main():
    args = parse_arguments()
    scrape_with_playwright(args)


if __name__ == "__main__":
    main()
