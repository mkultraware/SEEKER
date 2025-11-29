from curl_cffi import requests
from bs4 import BeautifulSoup
import smtplib
import json
import time
import datetime
import random
import re
import sys
import os
import shutil
from email.mime.text import MIMEText

# Playwright check
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(f"\033[91mCRITICAL: Playwright not installed. Run: pip install playwright && playwright install\033[0m")
    sys.exit(1)

# ================= GLOBAL COLORS =================
PURPLE = "\033[95m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
WHITE = "\033[97m"
RESET = "\033[0m"

# ================= CONFIGURATION =================
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# INSTRUKTIONER FÖR NYA ANVÄNDARE:
# 1. Byt ut "DIN_EMAIL@GMAIL.COM" mot din egen Gmail-adress.
# 2. Byt ut "DITT_APP_LOSENORD" mot ett Google App Password (inte ditt vanliga lösenord).
#    Guide: Gå till Google Account > Security > 2-Step Verification > App passwords.
SMTP_PASSWORD = "DITT_APP_LOSENORD"  
EMAIL_ADDRESS = "DIN_EMAIL@GMAIL.COM" 

# HEADLESS MODE: MUST BE FALSE FOR KOMPLETT TO WORK
# Kept False as requested, but optimized args below for the 12-inch MacBook.
HEADLESS_MODE = False 

# Log management
START_TIME = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
LOG_FILE = f"debug_log_{START_TIME}.html"

# LINKS LIST
LINKS = [
    "https://www.webhallen.com/se/category/47-Grafikkort-GPU?f=attributes%5Ecustom.cnet_videoutgang_chiptillverkare_906-1-NVIDIA%20Geforce", 
    "https://www.inet.se/kategori/167/geforce-rtx",
    "https://www.inet.se/fyndhornan?filter=%7B%22templateId%22%3A17%7D", 
    "https://www.proshop.se/Grafikkort?pre=0&f~grafikkort_videoudganggrafikprocessorleverandor=nvidia-geforce-rtx-5080~nvidia-geforce-rtx-5090", 
    "https://www.komplett.se/category/10412/datorutrustning/datorkomponenter/grafikkort",
    "https://www.elgiganten.se/gaming/datorkomponenter/grafikkort-gpu/nvidia-grafikkort",
    "https://www.netonnet.se/art/datorkomponenter/grafikkort/nvidia",
    "https://www.amazon.se/s?k=nvidia+geforce+rtx+graphics+card",
    "https://www.proshop.se/Demoprodukter",     
    "https://www.proshop.se/Outlet",           
    "https://www.netonnet.se/art/outlet",      
    "https://www.netonnet.se/art/fyndvaror"    
]

# PRICE TARGETS
PRICE_TARGETS = {
    "5090": 10000,
    "5080": 5000,
    "4090": 8000 
}

CHECK_INTERVAL = 180 
TOTAL_SCANNED_THIS_WEEK = 0
failed_sites = []

def get_random_headers():
    user_agents = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15"
    ]
    return {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Upgrade-Insecure-Requests": "1"
    }

def clean_price(price_str):
    if not price_str: return 0.0
    if isinstance(price_str, (int, float)):
        price_str = str(price_str)
        
    price_str = str(price_str).lower().strip()
    price_str = price_str.replace('fr.', '').replace(':-', '').replace('kr', '').replace('sek', '').replace('€', '').replace('$', '').replace('st', '') 
    price_str = price_str.replace('\xa0', '').replace(' ', '')
    
    clean = re.sub(r'[^\d,.]', '', price_str)
    if not clean: return 0.0
    if ',' in clean and '.' in clean: clean = clean.replace(',', '')
    elif ',' in clean:
        parts = clean.split(',')
        if len(parts) == 2 and len(parts[1]) == 2: clean = clean.replace(',', '.')
        else: clean = clean.replace(',', '')
    try: 
        price = float(clean)
        if 1000 <= price <= 150000: return price 
        elif 10 <= price < 1000: return price * 1000
        else: return 0.0
    except ValueError: return 0.0

def fetch_with_playwright(url, domain):
    api_data = []
    clean_domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
    if "www." in clean_domain:
        clean_domain = clean_domain.replace("www.", "")
    
    try:
        with sync_playwright() as p:
            user_data_dir = f"./chrome_profile_{random.randint(1000,9999)}"
            
            # === MACBOOK 12" OPTIMIZATION ARGS ===
            # These arguments reduce load on the Core M processor and weak GPU.
            launch_args = [
                '--disable-blink-features=AutomationControlled',
                '--no-default-browser-check',
                '--disable-infobars',
                '--disable-features=IsolateOrigins,site-per-process', 
                '--mute-audio',
                '--window-size=1024,768', # Smaller window = less pixels to render
                '--force-device-scale-factor=1', # CRITICAL: Disables Retina rendering to save GPU
                '--disable-smooth-scrolling', # Saves CPU cycles
                '--disable-background-timer-throttling',
                '--disable-renderer-backgrounding'
            ]
            
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir, 
                headless=HEADLESS_MODE, 
                viewport={'width': 1024, 'height': 768}, # Matched to window size
                locale='sv-SE',
                java_script_enabled=True,
                user_agent=get_random_headers()["User-Agent"],
                args=launch_args
            )
            
            page = context.pages[0]
            
            def handle_response(response):
                try:
                    ct = response.headers.get('content-type', '').lower()
                    if response.status == 200 and ('json' in ct or 'application/graphql' in ct):
                        try:
                            data = response.json()
                            if isinstance(data, (dict, list)):
                                api_data.append(data)
                        except: pass
                except: pass
            
            page.on("response", handle_response)
            
            page.add_init_script("""
                () => {
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.navigator.chrome = { runtime: {} };
                    Object.defineProperty(navigator, 'languages', { get: () => ['sv-SE', 'sv', 'en-US', 'en'] });
                }
            """)
            
            print(f"{YELLOW}[PW] Navigating to {clean_domain}...{RESET}", end="", flush=True)
            
            try:
                # WAIT STRATEGY
                wait_strat = "networkidle" if "netonnet" in domain else "domcontentloaded"
                page.goto(url, timeout=60000, wait_until=wait_strat)
            except Exception as e:
                pass

            # Cookie Nuke
            page.evaluate("""
                () => {
                    const acceptSelectors = ['#coiConsentBannerAccept', '#onetrust-accept-btn-handler', 'button[id*="accept"]', 'button[class*="accept"]', '[data-testid="cookie-banner-accept-all"]'];
                    acceptSelectors.forEach(s => { const el = document.querySelector(s); if(el) el.click(); });
                    
                    setTimeout(() => {
                        const selectors = ['#coiConsentBanner', '#CybotCookiebotDialog', '.cookie-consent', '#onetrust-consent-sdk', '.modal-backdrop', '.overlay', 'div[class*="modal"]'];
                        selectors.forEach(s => { document.querySelectorAll(s).forEach(el => el.remove()); });
                    }, 1000);
                }
            """)
            
            time.sleep(2) 
            
            # Scroll
            scroll_sleep = 1.0 if "netonnet" in domain else 0.5
            for i in range(5):
                try:
                    page.keyboard.press("PageDown")
                    time.sleep(scroll_sleep)
                except: pass
            
            content = page.content()
            context.close()
            try:
                if os.path.exists(user_data_dir):
                    shutil.rmtree(user_data_dir, ignore_errors=True)
            except: pass
            
            print(f" {GREEN}[SUCCESS: {len(content)} chars | {len(api_data)} APIs]{RESET}", end="", flush=True)
            return 200, content, api_data

    except Exception as e:
        print(f" {RED}[PW FATAL: {e}]{RESET}", end="", flush=True)
        return 500, str(e), []

def fetch_page_content(url):
    domain = url.split('/')[2]
    
    # Mandatory Playwright list
    if any(site in domain for site in ["webhallen.com", "elgiganten.se", "netonnet.se", "proshop.se", "inet.se", "komplett.se", "amazon.se"]):
        return fetch_with_playwright(url, domain)

    try:
        clean_domain = domain.replace("https://", "").replace("www.", "")
        print(f"{YELLOW}[REQ] Navigating to {clean_domain}...{RESET}", end="", flush=True)
        headers = get_random_headers()
        impersonation = random.choice(["chrome120", "chrome124", "safari15_3"])
        response = requests.get(url, headers=headers, impersonate=impersonation, timeout=30)
        print(f" {GREEN}[SUCCESS: {len(response.content)} chars]{RESET}", end="", flush=True)
        return response.status_code, response.content, []
    except Exception as e:
        print(f" {RED}[REQ FATAL: {e}]{RESET}", end="", flush=True)
        return 500, str(e), []

def save_clean_log(domain, soup, reason="Unknown"):
    try:
        debug_soup = BeautifulSoup(str(soup), "html.parser")
        for tag in debug_soup(["script", "style", "svg", "noscript", "path"]): tag.decompose()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_block = f"""
        <hr style="border-top: 5px solid red;">
        <h2 style="color: darkred; font-family: sans-serif;">FAILED: {domain}</h2>
        <p><strong>Time:</strong> {timestamp} | <strong>Reason:</strong> {reason}</p>
        <div style="background-color: #f4f4f4; padding: 15px; border: 1px solid #ccc; font-family: monospace; max-height: 400px; overflow-y: scroll;">
            {debug_soup.prettify()[:20000]} ... [truncated]
        </div><br>"""
        with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(error_block)
    except: pass

def recursive_product_finder(data, domain, found_list):
    if isinstance(data, dict):
        keys = {k.lower(): k for k in data.keys()}
        name_key = next((k for k in ['name', 'title', 'productname', 'displayname', 'text'] if k in keys), None)
        price_key = next((k for k in ['price', 'currentprice', 'priceamount', 'amount', 'value'] if k in keys), None)
        
        if name_key and price_key:
            name = data[keys[name_key]]
            price_raw = data[keys[price_key]]
            
            if isinstance(price_raw, dict):
                price_val = price_raw.get('value') or price_raw.get('amount') or price_raw.get('current')
            else:
                price_val = price_raw
                
            url_key = next((k for k in ['url', 'link', 'href', 'producturl', 'canonicalurl'] if k in keys), None)
            url = data[keys[url_key]] if url_key else None
            
            if not url:
                id_key = next((k for k in ['id', 'articleid', 'productid'] if k in keys), None)
                if id_key:
                    url = f"https://{domain}/product/{data[keys[id_key]]}"
            elif url and not url.startswith('http'):
                url = f"https://{domain}" + url

            if name and price_val and isinstance(name, str):
                p = clean_price(price_val)
                if p > 0 and len(name) > 3 and ".." not in name: 
                    found_list.append({'name': name, 'price': p, 'url': url or f"https://{domain}"})
        
        for v in data.values():
            recursive_product_finder(v, domain, found_list)
            
    elif isinstance(data, list):
        for item in data:
            recursive_product_finder(item, domain, found_list)

def extract_from_json(json_data, domain):
    found_items = []
    recursive_product_finder(json_data, domain, found_items)
    return found_items

# === ENHANCED REGEX SCANNER ===
def extract_regex_raw(soup, domain):
    found_items = []
    text = soup.get_text(" ", strip=True)
    price_pattern = re.compile(r'(\d{1,3}(?: \d{3})*|\d+):-')
    matches = list(price_pattern.finditer(text))
    
    for match in matches:
        price_str = match.group(1)
        price = clean_price(price_str)
        if price < 1000: continue
        
        start = max(0, match.start() - 300)
        end = match.start()
        context = text[start:end]
        
        keywords = ["RTX", "GeForce", "Radeon", "RX", "XT", "Grafikkort", "Gaming"]
        if any(k in context for k in keywords):
            parts = re.split(r'[|•\n]', context)
            potential_name = parts[-1].strip()
            if len(potential_name) < 10 and len(parts) > 1: 
                potential_name = parts[-2].strip() + " " + potential_name
            
            potential_name = potential_name.replace("Lagerstatus", "").replace("Webblager", "").strip()
            
            if len(potential_name) > 5 and len(potential_name) < 100:
                search_url = f"https://{domain}/search?q={potential_name.replace(' ', '+')}"
                found_items.append({'name': potential_name, 'price': price, 'url': search_url})
    return found_items

def extract_json_ld(soup, domain):
    found_items = []
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            data = json.loads(script.string)
            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                item_type = entry.get('@type', '')
                if 'Product' in item_type:
                    name = entry.get('name')
                    offers = entry.get('offers', {})
                    if isinstance(offers, list): offers = offers[0]
                    price = offers.get('price')
                    url = entry.get('url') or offers.get('url')
                    if name and price:
                        p = clean_price(price)
                        if not url: url = f"https://{domain}"
                        if p > 0: found_items.append({'name': name, 'price': p, 'url': url})
                elif 'ItemList' in item_type:
                    items = entry.get('itemListElement', [])
                    for item in items:
                        product = item.get('item', {})
                        if not product and 'name' in item: product = item
                        name = product.get('name')
                        price = None
                        offers = product.get('offers', {})
                        if isinstance(offers, dict): price = offers.get('price')
                        elif isinstance(offers, list) and offers: price = offers[0].get('price')
                        url = product.get('url')
                        if name and price:
                            p = clean_price(price)
                            if p > 0: found_items.append({'name': name, 'price': p, 'url': url})
        except: continue
    return found_items

def parse_products(soup, domain, url, api_data=[]):
    found_items = []

    try:
        ld_items = extract_json_ld(soup, domain)
        if ld_items:
            print(f"{GREEN}[JSON-LD]{RESET}", end="", flush=True)
            found_items.extend(ld_items)
            if len(found_items) > 0: return found_items
    except: pass
    
    if api_data:
        try:
            json_items = extract_from_json(api_data, domain)
            if json_items:
                print(f"{GREEN}[API]{RESET}", end="", flush=True)
                found_items.extend(json_items)
                return found_items
        except: pass

    if "netonnet.se" in domain:
        scripts = soup.find_all('script')
        for script in scripts:
            if not script.string: continue
            content = script.string.strip()
            matches = re.findall(r'(=|:)\s*(\{.*?\})\s*;?$', content, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match[1])
                    found_items.extend(extract_from_json([data], domain))
                except: pass
        if found_items: 
            print(f"{GREEN}[SCRIPT_DUMP]{RESET}", end="", flush=True)
            return found_items
            
        regex_items = extract_regex_raw(soup, domain)
        if regex_items:
            print(f"{GREEN}[RAW_REGEX]{RESET}", end="", flush=True)
            found_items.extend(regex_items)
            return found_items

    if "proshop.se" in domain:
        try:
            items = soup.select("div.product-list li.product, li.toggle, div.row li")
            for item in items:
                try:
                    name_el = item.select_one("a.site-product-link h2, a h2, h2.product-display-name")
                    price_el = item.select_one("span.site-currency-lg, span.price, .site-currency-attention")
                    if name_el and price_el:
                        name = name_el.get_text(strip=True)
                        price = price_el.get_text(strip=True)
                        link = item.select_one("a")['href']
                        if not link.startswith("http"): link = "https://www.proshop.se" + link
                        p = clean_price(price)
                        if p > 0: found_items.append({"name": name, "price": p, "url": link})
                except: continue
        except: pass
        if found_items: return found_items

    if "elgiganten.se" in domain:
        try:
            items = soup.select("article, div[class*='ProductCard']")
            for item in items:
                try:
                    link_el = item.select_one("a[href*='/product/']")
                    if link_el:
                        name = link_el.get_text(strip=True) or link_el.get("title")
                        price_el = item.select_one("[class*='Price'], [class*='price']")
                        if price_el:
                            price = clean_price(price_el.get_text(strip=True))
                            if price > 0: found_items.append({"name": name, "price": price, "url": f"https://www.elgiganten.se{link_el.get('href')}"})
                except: continue
        except: pass
        if found_items: return found_items

    if "komplett.se" in domain:
        try:
            result_tag = soup.find('komplett-search-results')
            if result_tag and result_tag.has_attr('preloadedsearchresult'):
                json_data = json.loads(result_tag['preloadedsearchresult'])
                products = json_data.get('products') or json_data.get('Products', [])
                for p in products:
                    name = p.get('Name') or p.get('name') or p.get('FullName')
                    price = p.get('Price') or p.get('DisplayPrice')
                    if not price and 'price' in p: price = p['price'].get('listPrice')
                    if name and price:
                        p_url = "https://www.komplett.se" + p.get('Url', p.get('url', ''))
                        cleaned_price = clean_price(price)
                        if cleaned_price > 0: found_items.append({'name': name, 'price': cleaned_price, 'url': p_url})
        except: pass
        return found_items

    if "webhallen.com" in domain:
        try:
            selectors = ['div.product-item', 'article.product', 'div[class*="product"]', 'a[href*="/product/"]']
            for selector in selectors:
                items = soup.select(selector)
                if len(items) > 3:
                    for item in items[:50]:
                        try:
                            link_el = item if item.name == 'a' else item.select_one('a')
                            if not link_el: continue
                            name_el = item.select_one('h2, h3, [class*="title"], [class*="name"]')
                            if not name_el: continue
                            name = name_el.get_text(strip=True)
                            
                            price_els = item.select('[class*="price"]')
                            valid_price = 0
                            for p_el in price_els:
                                p_text = p_el.get_text(strip=True)
                                if p_text.startswith("-") or "spara" in p_text.lower() or "ord" in p_text.lower(): continue
                                temp_price = clean_price(p_text)
                                if temp_price > 0:
                                    valid_price = temp_price
                                    break 
                            
                            link = link_el.get('href', '')
                            if link and not link.startswith('http'): link = "https://www.webhallen.com" + link
                            if len(name) > 5 and valid_price > 0: 
                                found_items.append({'name': name, 'price': valid_price, 'url': link})
                        except: continue
                    if found_items: break
        except: pass
        return found_items

    if "inet.se" in domain:
        try:
            items = soup.select('li[data-test-id^="search_product_"]')
            for item in items:
                try:
                    name = item.select_one('a[aria-label]').get('aria-label')
                    price = (item.select_one('span[class*="price"], .b1pydv7g') and item.select_one('span[class*="price"], .b1pydv7g').text.strip()) or ""
                    link = "https://www.inet.se" + item.select_one('a')['href']
                    cleaned_price = clean_price(price)
                    if cleaned_price > 0: found_items.append({'name': name, 'price': cleaned_price, 'url': link})
                except: continue
        except: pass
        return found_items

    if "amazon." in domain:
        try:
            items = soup.select('[data-component-type="s-search-result"], div.s-result-item, div[data-asin]')
            for item in items:
                try:
                    name_el = item.select_one('h2 a span') or item.select_one('h2')
                    price_whole = item.select_one('.a-price-whole')
                    price_fraction = item.select_one('.a-price-fraction')
                    price = ""
                    if price_whole:
                        price = price_whole.get_text(strip=True) + ('.' + price_fraction.get_text(strip=True) if price_fraction else '')
                    elif item.select_one('.a-offscreen'):
                        price = item.select_one('.a-offscreen').get_text(strip=True)
                    link = item.select_one('a[href]')['href']
                    if link and not link.startswith('http'):
                        link = "https://www.amazon." + domain.split('.')[-1] + link
                    name = name_el.get_text(strip=True) if name_el else ''
                    p = clean_price(price)
                    if p > 0: found_items.append({'name': name, 'price': p, 'url': link})
                except: continue
        except: pass
        return found_items

    try:
        selectors = ['div.product', 'article.product', 'li.product', 'div.search-hit-item', 'div.product-tile', 'div.c-productCard', 'div.product-card']
        for selector in selectors:
            items = soup.select(selector)
            if len(items) >= 2:
                for item in items[:200]:
                    try:
                        name = (item.select_one('h2, h3, .title, .name') and item.select_one('h2, h3, .title, .name').get_text(strip=True)) or (item.select_one('a') and item.select_one('a').get_text(strip=True))
                        price_el = item.select_one('[data-price], .price, [class*="price"]')
                        if not price_el: continue
                        p_text = price_el.get_text(strip=True)
                        if p_text.startswith("-") or "spara" in p_text.lower(): continue
                        price = price_el.get("data-price") if price_el.get("data-price") else p_text
                        link_el = item.select_one('a[href]')
                        link = link_el.get('href') if link_el else url
                        if link and not link.startswith('http'): link = "https://" + domain + link
                        p = clean_price(price)
                        if name and p > 0: found_items.append({'name': name, 'price': p, 'url': link})
                    except: continue
                if found_items: break
    except: pass

    return found_items

def send_mail(url, price, name):
    try:
        msg = MIMEText(f"Found deal!\n\nProduct: {name}\nPrice: {price} SEK\nLink: {url}")
        msg['Subject'] = f"GPU ALERT: {name} - {price} SEK"
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = EMAIL_ADDRESS
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, SMTP_PASSWORD)
            server.send_message(msg)
            print(f"{GREEN}Email sent for {name} ({price} SEK){RESET}")
    except Exception as e:
        print(f"{RED}Failed to send email: {e}{RESET}")

def log_scan_summary():
    if failed_sites:
        print(f"\n{RED}{'='*70}")
        print("SCAN FAILURES REPORT:")
        log_content = f"\n<br><br><h2 style='color: darkred;'>SCAN FAILURES REPORT:</h2>\n<ol>\n"
        for i, failure in enumerate(failed_sites):
            error_message = f"Error {i+1}: {failure['domain']} failed reason: {failure['reason']}"
            print(f"  {error_message}")
            log_content += f"<li>{failure['domain']} failed reason: {failure['reason']}</li>\n"
        print(f"{'='*70}{RESET}")
        log_content += "</ol>"
        with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(log_content)
    
def check_prices():
    global TOTAL_SCANNED_THIS_WEEK
    global failed_sites
    failed_sites = [] 

    print(f"\n{PURPLE}{'='*70}")
    print(f"Scan started at {datetime.datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*70}{RESET}")
    
    for url in LINKS:
        domain = url.split('/')[2]
        # === MACBOOK COOL-DOWN PAUSE ===
        # Passive cooling needs a moment to breathe between URLs
        time.sleep(2.0)
        
        try:
            result = fetch_page_content(url)
            status = result[0]
            content = result[1]
            api_data = result[2] if len(result) > 2 else []
            if status in [403, 503]:
                reason = f"BLOCKED ({status})"
                print(f" {RED}{reason}{RESET}")
                failed_sites.append({'domain': domain, 'reason': reason})
                continue
            if status != 200:
                reason = f"HTTP ERROR ({status})"
                print(f" {RED}{reason}{RESET}")
                failed_sites.append({'domain': domain, 'reason': reason})
                continue
            soup = BeautifulSoup(content, "html.parser")
            products = parse_products(soup, domain, url, api_data)
            
            # --- NETONNET OUTLET LOGIC ---
            if not products:
                is_netonnet_outlet = "netonnet.se" in domain and ("outlet" in url or "fyndvaror" in url)
                if is_netonnet_outlet:
                    print(f" {GREEN}No GPUs in Outlet (Checked){RESET}")
                else:
                    reason = "No products found"
                    print(f" {RED}{reason}{RESET}")
                    save_clean_log(domain, soup, reason)
                    failed_sites.append({'domain': domain, 'reason': reason})
                continue
                
            count = len(products)
            TOTAL_SCANNED_THIS_WEEK += count
            deals = 0
            for p in products:
                name_up = p['name'].upper()
                price = p['price']
                target_price = 0
                if "5090" in name_up: target_price = PRICE_TARGETS["5090"]
                elif "5080" in name_up: target_price = PRICE_TARGETS["5080"]
                elif "4090" in name_up: target_price = PRICE_TARGETS["4090"]
                if target_price > 0 and 1000 < price < target_price:
                    send_mail(p['url'], price, p['name'])
                    deals += 1
            color = GREEN if deals == 0 else PURPLE
            print(f" {color}Found {count} items, {deals} deals{RESET}")
        except Exception as e:
            reason = f"CRASH: {str(e)[:50]}..."
            print(f" {RED}{reason}{RESET}")
            failed_sites.append({'domain': domain, 'reason': reason})

    print(f"\n{PURPLE}{'='*70}")
    print(f"Scan complete - Total scanned this week: {TOTAL_SCANNED_THIS_WEEK}")
    print(f"{'='*70}{RESET}\n")
    log_scan_summary()

if __name__ == "__main__":
    print(f"\n{PURPLE}{'='*80}")
    print(f"          GPU PRICE SNIPER - by JETSKii")
    print(f"          Optimized for MacBook 12 (Retina 2015)")
    print(f"{'='*80}{RESET}")
    print(f"Log file: {LOG_FILE}")
    print(f"Targets: RTX 5090 < {PRICE_TARGETS['5090']} SEK | RTX 5080 < {PRICE_TARGETS['5080']} SEK | RTX 4090 < {PRICE_TARGETS['4090']} SEK")
    print(f"Check interval: {CHECK_INTERVAL}s")
    print(f"{PURPLE}{'='*80}{RESET}\n")
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"<h1>GPU Sniper - Started {START_TIME}</h1>")
    while True:
        try:
            check_prices()
            print(f"Next scan in {CHECK_INTERVAL} seconds...\n")
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print(f"\n{PURPLE}{'='*70}")
            print("Shutting down gracefully...")
            print(f"{'='*70}{RESET}\n")
            break
        except Exception as e:
            print(f"{RED}Main loop error: {e}{RESET}")
            time.sleep(60)