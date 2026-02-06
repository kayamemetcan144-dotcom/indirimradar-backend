import requests
from bs4 import BeautifulSoup
import re
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import shutil
import os

class ProductScraper:
    def __init__(self, headless=True):
        self.headless = headless

    def setup_selenium(self):
        print("🕵️‍♂️ Chrome başlatılıyor...")
        chrome_path = shutil.which("chromium") or shutil.which("google-chrome") or "/usr/bin/chromium"
        driver_path = shutil.which("chromedriver") or "/usr/bin/chromedriver"
        
        if not os.path.exists(chrome_path): chrome_path = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
        if not os.path.exists(driver_path): driver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

        chrome_options = Options()
        if self.headless: chrome_options.add_argument('--headless')
        
        # Bot Tespitini Aşma (Anti-Detection)
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        # Gerçek bir kullanıcı gibi görünmek için User-Agent
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
        
        chrome_options.binary_location = chrome_path

        from selenium.webdriver.chrome.service import Service
        try:
            service = Service(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            return driver
        except Exception as e:
            print(f"❌ Driver hatası: {str(e)}")
            raise e

    def scrape_single_product(self, url):
        print(f"🔗 İnceleniyor: {url}")
        driver = self.setup_selenium()
        
        # Varsayılan Boş Veri
        product_data = {
            'title': 'Ürün Başlığı Bulunamadı',
            'current_price': 0.0,
            'original_price': 0.0,
            'discount_percent': 0,
            'image_url': '',
            'product_url': url,
            'platform': 'Hepsiburada',
            'category': 'Genel'
        }

        try:
            driver.get(url)
            time.sleep(3) # Sayfanın yüklenmesini bekle
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # === 1. FİYAT BULMA (3 Aşamalı Kontrol) ===
            current_price = 0.0
            original_price = 0.0

            # YÖNTEM A: Script Regex (En Güvenilir - Taksit Fiyatını Atlar)
            # Sayfa kodunda 'currentPrice': 64.99 gibi yazan yeri bulur
            try:
                # currentPrice veya price değişkenini ara
                matches = re.findall(r'"currentPrice":\s*([\d\.]+)', page_source)
                if not matches:
                    matches = re.findall(r'"price":\s*([\d\.]+)', page_source)
                
                valid_prices = []
                for m in matches:
                    p = float(m)
                    if p > 15: # 15 TL altı (Taksit vb.) filtrele
                        valid_prices.append(p)
                
                if valid_prices:
                    current_price = min(valid_prices) # En düşük geçerli fiyat satış fiyatıdır
                    print(f"💰 Script Fiyatı Bulundu: {current_price}")
                    
                    # Eski fiyatı da script'ten ara
                    orig_matches = re.findall(r'"originalPrice":\s*([\d\.]+)', page_source)
                    if orig_matches:
                        original_price = float(orig_matches[0])
            except: pass

            # YÖNTEM B: CSS Selectors (Etiket Okuma) - Yedek
            if current_price == 0:
                price_box = soup.find(['span', 'div'], {'data-test-id': 'price-current-price'})
                if price_box:
                    current_price = self.parse_price(price_box.text)
                    print(f"💰 Etiket Fiyatı Bulundu: {current_price}")
                
                old_price_box = soup.find(['span', 'div'], {'data-test-id': 'price-old-price'})
                if old_price_box:
                    original_price = self.parse_price(old_price_box.text)

            # YÖNTEM C: JSON-LD (Google Verisi) - Son Çare
            if current_price == 0:
                scripts = soup.find_all('script', type='application/ld+json')
                for script in scripts:
                    if 'offers' in script.text:
                        try:
                            data = json.loads(script.text)
                            if isinstance(data, list): data = data[0]
                            offer = data.get('offers', {})
                            if isinstance(offer, list): offer = offer[0]
                            current_price = float(str(offer.get('price', 0)))
                            break
                        except: pass

            # === 2. RESİM BULMA ===
            image_url = ""
            
            # Öncelik 1: OpenGraph (Facebook Resmi)
            og_img = soup.find("meta", property="og:image")
            if og_img: image_url = og_
