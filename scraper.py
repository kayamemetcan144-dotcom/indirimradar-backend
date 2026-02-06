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
        
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
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
        product_data = None
        
        try:
            driver.get(url)
            time.sleep(5) # İyice yüklenmesini bekle
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # --- 1. RESİM BULMA (Gelişmiş) ---
            image_url = ""
            # A) OpenGraph
            og_img = soup.find("meta", property="og:image")
            if og_img: image_url = og_img["content"]
            
            # B) Hepsiburada Özel JSON (window.productModel)
            if not image_url:
                try:
                    # Sayfa kaynağında "image" kelimesini içeren JSON yapılarını ara
                    matches = re.findall(r'"image"\s*:\s*"([^"]+)"', page_source)
                    for m in matches:
                        if "http" in m and ("jpg" in m or "png" in m):
                            image_url = m.replace("\\", "") # Linki temizle
                            break
                except: pass

            # C) Gallery/Slider içinden
            if not image_url:
                img_tags = soup.find_all('img')
                for img in img_tags:
                    src = img.get('src', '')
                    # Ürün resmi genelde büyük olur ve 'product' kelimesi geçebilir
                    if src.startswith('http') and ('mnresize' in src or 'product' in src) and not 'svg' in src:
                        image_url = src
                        break

            # --- 2. FİYAT BULMA (Regex ile Kaba Kuvvet) ---
            current_price = 0.0
            
            # A) Sayfa kaynağındaki tüm "price": 123.45 kalıplarını bul
            # Örnek: "price":123.45 veya "currentPrice":123.45
            price_patterns = [
                r'"price"\s*:\s*([\d\.]+)', 
                r'"currentPrice"\s*:\s*([\d\.]+)',
                r'"amount"\s*:\s*([\d\.]+)',
                r'"value"\s*:\s*([\d\.]+)'
            ]
            
            for pattern in price_patterns:
                matches = re.findall(pattern, page_source)
                for m in matches:
                    try:
                        p = float(m)
                        if p > 10: # 10 TL'den küçükse muhtemelen hatalı veridir
                            current_price = p
                            print(f"💰 Regex Fiyat Bulundu: {current_price}")
                            break
                    except: continue
                if current_price > 0: break

            # B) HTML Etiketlerinde Ara (Yedek)
            if current_price == 0:
                # "1.234,56 TL" formatını ara
                html_text = soup.get_text()
                # TL simgesi olan rakamları bul
                tl_prices = re.findall(r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*TL', html_text)
                for p_str in tl_prices:
                    p = self.parse_price(p_str)
                    if p > 10:
                        current_price = p
                        print(f"💰 HTML Fiyat Bulundu: {current_price}")
                        break

            # --- 3. BAŞLIK BULMA ---
            title = "Ürün Başlığı"
            if soup.title: title = soup.title.string.strip()
            og_title = soup.find("meta", property="og:title")
            if og_title: title = og_title["content"].strip()

            # Verileri Paketle
            product_data = {
                'title': title,
                'current_price': current_price,
                'original_price': current_price,
                'discount_percent': 0,
                'image_url': image_url,
                'product_url': url,
                'platform': 'Hepsiburada' if 'hepsiburada' in url else 'Diğer',
                'category': 'Genel'
            }
                
        except Exception as e:
            print(f"❌ Hata: {e}")
        finally:
            driver.quit()
            
        return product_data

    def parse_price(self, text):
        if not text: return 0.0
        # 1.234,50 -> 1234.50 dönüşümü
        clean = re.sub(r'[^\d,]', '', text)
        clean = clean.replace(',', '.')
        try:
            return float(clean)
        except:
            return 0.0
