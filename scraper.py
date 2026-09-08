#!/usr/bin/env python3
"""
Behatsdaa Participating Stores Multi-Card Scraper (Modular Refactor)
"""

import os
import sys
import json
import re
import csv
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

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
    if isinstance(text, (int, float)):
        return int(text)
    match = re.search(r'(\d+(?:\.\d+)?)\s*%', str(text))
    if match:
        try:
            return int(float(match.group(1)))
        except ValueError:
            pass
    match = re.search(r'(\d+)', str(text))
    if match:
        val = int(match.group(1))
        if 1 <= val <= 100:
            return val
    return 0


def generate_store_id(name, fallback_index=0):
    """Generate a clean URL-friendly identifier for a store."""
    slug = re.sub(r'[^a-zA-Z0-9\u0590-\u05FF]+', '-', str(name)).strip('-').lower()
    return slug or f"store-{fallback_index}"


def parse_chains_from_categories(categories, card_info):
    """Parse list of categories and chains returned by GetWalletChain API."""
    stores = []
    card_id = card_info["id"]
    card_name = card_info["name"]
    card_discount_str = card_info["discount_default"]
    card_discount_num = card_info["discount_numeric"]

    for cat in categories:
        cat_name = (cat.get("tagName") or "כללי").strip()
        chains = cat.get("walletChainData") or []

        for chain in chains:
            name = (chain.get("chainName") or "").strip()
            if not name:
                continue

            # Filter out UI anomalies
            if any(bad in name for bad in ["סל קניות", "תעודת זהות", "לטעינה", "תשלום בקופה", "ביטול טעינה", "מספר כרטיס המועדון"]):
                continue

            stores.append({
                "name": name,
                "chain_id": str(chain.get("chainID") or ""),
                "category": cat_name,
                "logo": chain.get("logoURL") or "",
                "website": chain.get("webSite") or "",
                "card_id": card_id,
                "card_name": card_name,
                "discount": card_discount_str,
                "discount_numeric": card_discount_num,
                "conditions": ""
            })

    return stores


def merge_stores_into_catalog(catalog, stores, card_info):
    """
    Merge scraped stores into unified catalog with deduplication across cards.
    """
    card_id = card_info["id"]
    card_name = card_info["name"]
    discount_str = card_info["discount_default"]
    discount_num = card_info["discount_numeric"]

    for s in stores:
        sname = s["name"]
        if sname not in catalog:
            catalog[sname] = {
                "id": generate_store_id(sname, len(catalog) + 1),
                "name": sname,
                "category": s.get("category") or "כללי",
                "logo": s.get("logo") or "",
                "website": s.get("website") or "",
                "conditions": s.get("conditions") or "",
                "cards": [],
                "max_discount": 0
            }

        store_entry = catalog[sname]

        # Add card if not already linked
        linked_card_ids = {c["card_id"] for c in store_entry["cards"]}
        if card_id not in linked_card_ids:
            store_entry["cards"].append({
                "card_id": card_id,
                "card_name": card_name,
                "discount": discount_str,
                "discount_numeric": discount_num,
                "notes": s.get("conditions") or ""
            })

        # Update maximum discount
        if discount_num > store_entry["max_discount"]:
            store_entry["max_discount"] = discount_num

        # Update category if previously unclassified
        if store_entry["category"] in ["כללי", "אחר"] and s.get("category"):
            store_entry["category"] = s["category"]

        # Backfill logo and website if missing
        if not store_entry["logo"] and s.get("logo"):
            store_entry["logo"] = s["logo"]
        if not store_entry["website"] and s.get("website"):
            store_entry["website"] = s["website"]




def launch_stealth_context(p, profile_dir, headless=False, channel=None):
    """Launch Chromium context with stealth flags to bypass Incapsula WAF."""
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

            return p.chromium.launch_persistent_context(**kwargs)
        except Exception as e:
            msg = str(e).split('\n')[0]
            if ch:
                print(f"[*] Channel '{ch}' not available ({msg}), trying next option...")
            else:
                print(f"[!] Bundled Chromium launch failed: {msg}")

    raise RuntimeError("Could not launch any browser! Please run: playwright install chromium")


def wait_for_user_login(page):
    """Detect if page redirected to /login and wait for user authentication."""
    try:
        is_login = "/login" in page.url or page.locator("input[type='tel'], input[placeholder*='תעודת'], button:has-text('כניסה')").count() > 0
    except Exception:
        is_login = "/login" in page.url

    if is_login:
        print("\n" + "=" * 65)
        print(" [!] ACTION REQUIRED: Behatsdaa Login Needed")
        print("=" * 65)
        print(" Behatsdaa requires logging in to access cards and participating stores.")
        print(" -> Enter your ID & SMS code in the opened Chrome/Edge window.")
        try:
            input(" -> Once you are logged in on screen, press [Enter] here to continue: ")
            print("[+] Login confirmed! Resuming scraper...")
            page.wait_for_timeout(2000)
        except Exception:
            pass
        print("=" * 65 + "\n")


def fetch_wallets_via_evaluate(page):
    """Execute high-speed API extraction inside active browser session."""
    return page.evaluate("""
        async () => {
            const headers = {
                "OrganizationId": "20",
                "Accept": "application/json"
            };

            // 1. Retrieve all cards/wallets
            let wallets = [];
            try {
                const genRes = await window.fetch("https://back.behatsdaa.org.il/api/cards/GetCardGeneralInfo", {
                    headers,
                    credentials: "include"
                });
                const genJson = await genRes.json();
                wallets = genJson?.data?.wallets || [];
            } catch (e) {
                return { error: 'GetCardGeneralInfo failed: ' + e.toString() };
            }

            if (!wallets || wallets.length === 0) {
                return { error: 'No wallets returned from GetCardGeneralInfo' };
            }

            // 2. Fetch all stores for each wallet
            const results = [];
            for (const w of wallets) {
                const wid = w.walletID;
                try {
                    const chainRes = await window.fetch(`https://back.behatsdaa.org.il/api/cards/GetWalletChain?walletId=${wid}`, {
                        headers,
                        credentials: "include"
                    });
                    const chainJson = await chainRes.json();
                    results.push({
                        wallet: w,
                        categories: chainJson?.data || []
                    });
                } catch (err) {
                    results.push({
                        wallet: w,
                        error: err.toString(),
                        categories: []
                    });
                }
            }
            return { ok: true, results };
        }
    """)


def save_catalog(final_stores_list, discovered_cards, output_dir, card_url):
    """Save finalized stores list into stores.json and stores.csv."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "stores.json"
    csv_path = output_dir / "stores.csv"

    # Categories list
    all_categories = sorted(list({s.get("category", "כללי") for s in final_stores_list if s.get("category")}))
    if "הכל" not in all_categories:
        all_categories.insert(0, "הכל")

    output_payload = {
        "metadata": {
            "title": "רשימת רשתות מכבדות - כרטיסי בהצדעה",
            "source": card_url,
            "last_updated": datetime.now(timezone.utc).isoformat(),
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


def scrape_with_playwright(args):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n[ERROR] Playwright is not installed! Run: pip install -r requirements.txt\n")
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
            print(f"[*] Connecting over CDP: {endpoint} ...")
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

        # Stealth flag
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")

        # Network interceptor as safety net
        def handle_response(response):
            try:
                url = response.url
                if ("back.behatsdaa.org.il" in url or "cards" in url.lower() or "shops" in url.lower()) and "json" in response.headers.get("content-type", ""):
                    try:
                        intercepted_api_data[url] = response.json()
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", handle_response)

        # 1. Navigate to main chargingCard page
        print(f"\n[1/3] Navigating to: {args.card_url}")
        try:
            page.goto(args.card_url, wait_until="domcontentloaded", timeout=args.timeout)
        except Exception as e:
            print(f"[*] Navigation note: {e}")

        # Check authentication
        wait_for_user_login(page)
        time.sleep(2)

        # 2. Extract Data via In-Browser API Execution
        print("\n[2/3] Extracting wallets and stores across all cards...")
        start_time = time.time()
        raw_result = None

        try:
            raw_result = fetch_wallets_via_evaluate(page)
        except Exception as err:
            print(f"[!] In-browser evaluation error: {err}")

        if raw_result and raw_result.get("ok"):
            results = raw_result.get("results", [])
            print(f"[+] Successfully retrieved data for {len(results)} cards in {time.time() - start_time:.2f}s!")

            for item in results:
                w = item["wallet"]
                wid = str(w.get("walletID"))
                wname = (w.get("walletName") or f"כרטיס ארנק {wid}").strip()
                disc_num = extract_discount_percent(w.get("discountRate", 0))
                disc_str = f"{disc_num}%" if disc_num else "הנחת מועדון"

                card_entry = {
                    "id": f"card-{wid}",
                    "name": wname,
                    "wallet_id": wid,
                    "discount_default": disc_str,
                    "discount_numeric": disc_num,
                    "max_deposit": w.get("maxDeposit"),
                    "url": f"https://www.behatsdaa.org.il/card/shops?walletId={wid}"
                }
                discovered_cards.append(card_entry)

                categories = item.get("categories", [])
                stores = parse_chains_from_categories(categories, card_entry)
                print(f"    [*] Card '{wname}' (walletId {wid}): {len(stores)} participating stores (הנחה: {disc_str})")

                merge_stores_into_catalog(all_scraped_stores, stores, card_entry)

        else:
            # Fallback path
            print("[*] Direct API call fallback: navigating through cards...")
            wallets = []
            for url, json_data in intercepted_api_data.items():
                if "GetCardGeneralInfo" in url and isinstance(json_data, dict):
                    wallets = json_data.get("data", {}).get("wallets", [])
                    if wallets:
                        break

            if not wallets:
                wallets = [{"walletID": "3379", "walletName": "כרטיס בהצדעה ראשי", "discountRate": 20}]

            for w in wallets:
                wid = str(w.get("walletID"))
                wname = (w.get("walletName") or f"כרטיס ארנק {wid}").strip()
                disc_num = extract_discount_percent(w.get("discountRate", 0))
                disc_str = f"{disc_num}%" if disc_num else "הנחת מועדון"

                card_entry = {
                    "id": f"card-{wid}",
                    "name": wname,
                    "wallet_id": wid,
                    "discount_default": disc_str,
                    "discount_numeric": disc_num,
                    "url": f"https://www.behatsdaa.org.il/card/shops?walletId={wid}"
                }
                discovered_cards.append(card_entry)

                try:
                    page.goto(card_entry["url"], wait_until="domcontentloaded", timeout=args.timeout)
                    time.sleep(2)
                except Exception as e:
                    print(f"[*] Navigation note: {e}")

                categories = []
                for url, json_data in intercepted_api_data.items():
                    if "GetWalletChain" in url and wid in url and isinstance(json_data, dict):
                        categories = json_data.get("data", [])
                        if isinstance(categories, list) and categories:
                            break

                stores = parse_chains_from_categories(categories, card_entry) if categories else []
                print(f"[+] Found {len(stores)} stores for '{wname}'.")
                merge_stores_into_catalog(all_scraped_stores, stores, card_entry)

        context.close()

    final_stores_list = list(all_scraped_stores.values())
    print(f"\n==========================================================")
    print(f"[+] Total unique participating stores scraped: {len(final_stores_list)}")
    print(f"[+] Total unique cards discovered: {len(discovered_cards)}")
    print(f"==========================================================")

    if not final_stores_list:
        print("[!] No stores could be extracted during session.")
        return

    # Save to disk
    save_catalog(final_stores_list, discovered_cards, args.output_dir, args.card_url)
    print("\n[SUCCESS] Scraping completed successfully!")


def main():
    args = parse_arguments()
    scrape_with_playwright(args)


if __name__ == "__main__":
    main()
