# Behatsdaa Participating Stores Multi-Card Catalog 💳

> **Live Web Application:** [https://elonuziel.github.io/stores-list/](https://elonuziel.github.io/stores-list/)

A fast, interactive web catalog and automated scraper for all stores, restaurants, fashion brands, and attractions participating in **[Behatsdaa](https://www.behatsdaa.org.il/card/chargingCard)** recharge cards (Club Cards, Fighter Card, Restaurants, Carrefour, Online Grocery, and Special Promotions).

---

## 🚀 Live Demo & Features

Explore the catalog live at: **[https://elonuziel.github.io/stores-list/](https://elonuziel.github.io/stores-list/)**

- ⚡ **Ultra-Fast Search**: Real-time Hebrew search with diacritics and final-letter normalization (`ך/כ`, `ם/מ`, `ן/נ`, `ף/פ`, `ץ/צ`).
- 💳 **8 Distinct Cards & Wallets**: Filter by specific cards or view all participating stores across every card.
- 🏷️ **Accurate Multi-Card Discounts**: Clearly shows which cards are accepted at each brand and the exact discount rate for each (e.g. 30%, 20%, 18%, 15%, 10%, 7%).
- 🗂️ **Dynamic Categories**: Instant category filtering (Restaurants, Fashion, Spas, Travel & Vacations, Home & Living, Culture, etc.) with dynamic store count badges.
- 📊 **Dual Views**: Seamless toggle between responsive Grid Cards and compact Table View.
- 🌙 **Dark & Light Themes**: Full dark mode support with automatic system preference detection and local persistence.
- 📥 **Export Ready**: Download the complete catalog anytime as [stores.csv](data/stores.csv) (Excel-compatible UTF-8 BOM) or [stores.json](data/stores.json).
- 🔒 **Zero External AI Dependencies**: 100% self-contained and accurate data extracted directly from Behatsdaa's official systems.

---

## 📁 Project Structure

```text
stores-list/
├── index.html           # Main web application (GitHub Pages)
├── styles.css           # Custom RTL styling, dark theme, and animations
├── app.js               # Frontend search, filtering, and rendering logic
├── scraper.py           # High-speed multi-card Python Playwright scraper
├── requirements.txt     # Python dependencies
├── data/
│   ├── stores.json      # Structured JSON catalog (980+ stores, 8 cards)
│   └── stores.csv       # Excel-compatible CSV catalog
├── .github/workflows/
│   └── scrape.yml       # Automated weekly GitHub Actions scraper workflow
└── README.md            # Documentation and usage guide
```

---

## 🛠️ Scraper Installation & Usage

### 1. Prerequisites & Dependencies
Ensure Python 3.10+ is installed, then install required packages:

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Run the Scraper
Run the scraper using your preferred browser (Google Chrome or Microsoft Edge):

```bash
# Using Microsoft Edge (Default on Windows):
python scraper.py --browser edge

# Using Google Chrome:
python scraper.py --browser chrome

# Connect to an already running browser via CDP port:
python scraper.py --cdp 9222
```

> **Note on First Run / Authentication:**
> When running for the first time, a browser window will open. If you are prompted to log in with your Behatsdaa ID & SMS verification code, complete the login once in the window. The session is saved to `./behatsdaa_profile` so subsequent scrapes run completely automatically in ~5 seconds.

---

## 💻 Local Web Development

Because the web application is built with standard HTML5, Tailwind CSS, and Vanilla JavaScript (Zero-Build), you can run it locally with any simple HTTP server:

```bash
python -m http.server 8000
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

---

## 🌐 Automated Deployment (GitHub Pages)

The repository deploys automatically to GitHub Pages:
1. Pushing changes to the `main` branch immediately publishes to `https://elonuziel.github.io/stores-list/`.
2. The site incorporates dynamic cache-busting headers (`no-store` and version timestamps) to ensure visitors always receive the latest stores catalog upon refreshing.
3. A scheduled GitHub Action (`.github/workflows/scrape.yml`) runs weekly to keep the catalog fresh.

---

## 📄 License & Attribution
Created for the benefit of Israeli reserve soldiers (Miluim) and Behatsdaa club beneficiaries. Brand names, logos, and terms are property of [Behatsdaa](https://www.behatsdaa.org.il).
