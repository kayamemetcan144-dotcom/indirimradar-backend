import requests
from bs4 import BeautifulSoup
import re
import json
import time
import os
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

class ProductScraper:
    def __init__(self, headless=True):
        self.headless = headless

    def setup_selenium(self):
        chrome_bin = shutil.which("chromium") or shutil.which("google-chrome") or "/usr/bin/chromium"
        if os.environ.get("CHROME_BIN"): chrome_bin = os.environ.get("CHROME_BIN")
        chromedriver_bin = shutil.which("chromedriver") or "/usr/bin/chromedriver"
        if os.environ.get("CHROMEDRIVER_PATH"): chromedriver_bin = os.environ.get("CHROMEDRIVER_PATH")

        options = Options()
        if self.headless: options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        options.binary_location = chrome_bin

        try:
            service = Service(executable_path=chromedriver_bin)
            return webdriver.Chrome(service=service, options=options)
        except Exception as e:
            print(f"Driver Error: {e}")
            raise e

    def scrape_single_product(self, url):
        print(f"🔗 Scraping: {url}")
        data = {'title': 'Başlık Yok', 'current_price': 0.0, 'original_price': 0.0, 'discount_percent': 0, 'image_url': '', 'product_url': url, 'platform': 'Site', 'category': 'Genel', 'real_deal_status': 'normal'}
        
        if 'hepsiburada' in url: data['platform'] = 'Hepsiburada'
        elif 'trendyol' in url: data['platform'] = 'Trendyol'

        driver = None
        try:
            driver = self.setup_selenium()
            driver.get(url)
            time.sleep(5)
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # JSON-LD (Öncelikli)
            for s in soup.find_all('script', type='application/ld+json'):
                try:
                    j = json.loads(s.text)
                    if isinstance(j, list): j = j[0]
                    if 'offers' in j:
                        offer = j.get('offers', {})
                        if isinstance(offer, list): offer = offer[0]
                        price = float(str(offer.get('price', 0)))
                        if price > 15: data['current_price'] = price
                    if 'image' in j:
                        imgs = j['image']
                        if isinstance(imgs, list) and len(imgs) > 0: data['image_url'] = imgs[0]
                        elif isinstance(imgs, str): data['image_url'] = imgs
                    if 'name' in j: data['title'] = j['name']
                except: pass

            # Yedek Fiyat Arama
            if data['current_price'] == 0:
                script_prices = re.findall(r'"currentPrice":\s*([\d\.]+)', driver.page_source)
                for p in script_prices:
                    if float(p) > 15: 
                        data['current_price'] = float(p)
                        break

            # Eski Fiyat
            if data['current_price'] > 0:
                orig_matches = re.findall(r'"originalPrice":\s*([\d\.]+)', driver.page_source)
                valid_orig = [float(x) for x in orig_matches if float(x) > data['current_price']]
                if valid_orig: data['original_price'] = max(valid_orig)
                else: data['original_price'] = data['current_price']
                
                if data['original_price'] > data['current_price']:
                    diff = data['original_price'] - data['current_price']
                    data['discount_percent'] = int((diff / data['original_price']) * 100)
                    if data['discount_percent'] > 20: data['real_deal_status'] = 'real'

        except Exception as e:
            print(f"Scrape Error: {e}")
        finally:
            if driver: driver.quit()
        
        return data
