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
        # Railway ve Local uyumlu yol ayarları
        chrome_path = shutil.which("chromium") or shutil.which("google-chrome") or "/usr/bin/chromium"
        driver_path = shutil.which("chromedriver") or "/usr/bin/chromedriver"
        
        if not os.path.exists(chrome_path): chrome_path = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
        if not os.path.exists(driver_path): driver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

        options = Options()
        if self.headless: options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        # Hepsiburada'ya "Ben Chrome'um" diyoruz
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.binary_location = chrome_path

        try:
            service = Service(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=options)
            return driver
        except Exception as e:
            print(f"Driver Hatası: {e}")
            raise e

    def scrape_single_product(self, url):
        print(f"🔗 İnceleniyor: {url}")
        driver = self.setup_selenium()
        
        # Varsayılan Boş Şablon
        data = {
            'title': 'Başlık Bulunamadı',
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
            time.sleep(3) # Sayfa otursun diye bekle
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')

            # --- 1. RESİM (En Kolay ve Kesin Yöntem) ---
            # OpenGraph resmi her zaman doğrudur
            og_img = soup.find("meta", property="og:image")
            if og_img: 
                data['image_url'] = og_img["content"]
            else:
                # Bulamazsa Script içinden çek
                img_matches = re.findall(r'"image":\s*"([^"]+)"', page_source)
                for m in img_matches:
                    if "http" in m and "mnresize" in m:
                        data['image_url'] = m.replace("\\", "")
                        break

            # --- 2. FİYAT (Taksit Tuzağına Düşmeden) ---
            found_prices = []

            # A) Script içindeki 'currentPrice' (En Temiz Veri)
            # Regex: "currentPrice": 64.99 yapısını arar
            script_prices = re.findall(r'"currentPrice":\s*([\d\.]+)', page_source)
            for p in script_prices:
                val = float(p)
                if val > 25: found_prices.append(val) # 25 TL altı taksittir, alma!

            # B) JSON-LD (Google Verisi)
            if not found_prices:
                scripts = soup.find_all('script', type='application/ld+json')
                for s in scripts:
                    if 'offers' in s.text:
                        try:
                            j = json.loads(s.text)
                            if isinstance(j, list): j = j[0]
                            offer = j.get('offers', {})
                            if isinstance(offer, list): offer = offer[0]
                            p = float(str(offer.get('price', 0)))
                            if p > 25: found_prices.append(p)
                        except: pass

            # Karar Anı: Bulunan geçerli fiyatların en küçüğü fiyattır.
            if found_prices:
                data['current_price'] = min(found_prices)
                
                # Eski Fiyatı Bul (İndirim hesabı için)
                orig_matches = re.findall(r'"originalPrice":\s*([\d\.]+)', page_source)
                valid_orig = [float(x) for x in orig_matches if float(x) > data['current_price']]
                
                if valid_orig:
                    data['original_price'] = max(valid_orig)
                else:
                    data['original_price'] = data['current_price']

            # --- 3. BAŞLIK ---
            og_title = soup.find("meta", property="og:title")
            if og_title: 
                data['title'] = og_title["content"].split(" Fiyatı")[0]
            elif soup.title:
                data['title'] = soup.title.text.split(" Fiyatı")[0]

            # --- 4. HESAPLAMALAR ---
            if data['original_price'] > data['current_price']:
                diff = data['original_price'] - data['current_price']
                data['discount_percent'] = int((diff / data['original_price']) * 100)

        except Exception as e:
            print(f"Hata: {e}")
        finally:
            driver.quit()
        
        return data
