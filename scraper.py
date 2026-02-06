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
        # Railway ve Local yolları
        chrome_path = shutil.which("chromium") or shutil.which("google-chrome") or "/usr/bin/chromium"
        driver_path = shutil.which("chromedriver") or "/usr/bin/chromedriver"
        
        if not os.path.exists(chrome_path): chrome_path = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
        if not os.path.exists(driver_path): driver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

        chrome_options = Options()
        if self.headless: chrome_options.add_argument('--headless')
        
        # Bot engellerini aşmak için kritik ayarlar
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
            time.sleep(3) # Sayfa otursun
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # --- 1. HEPSİBURADA FİYAT (Nokta Atışı) ---
            current_price = 0.0
            original_price = 0.0
            
            # A) Güncel Fiyat (Yeşil/Büyük Olan)
            # Hepsiburada'nın kullandığı net etiket: 'price-current-price'
            price_box = soup.find(['div', 'span'], {'data-test-id': 'price-current-price'})
            if price_box:
                current_price = self.parse_price(price_box.text)
                print(f"✅ Güncel Fiyat Bulundu: {current_price}")
            
            # B) Eski Fiyat (Üstü Çizili Olan)
            old_price_box = soup.find(['div', 'span'], {'data-test-id': 'price-old-price'})
            if old_price_box:
                original_price = self.parse_price(old_price_box.text)
                print(f"✅ Eski Fiyat Bulundu: {original_price}")

            # --- 2. YEDEK PLAN (Eğer Site Tasarımı Değişmişse) ---
            if current_price == 0:
                print("⚠️ Etiketle bulunamadı, JSON verisine bakılıyor...")
                # Hepsiburada sayfa içinde 'productModel' adında bir JSON tutar
                scripts = soup.find_all('script')
                for script in scripts:
                    if 'currentPrice' in script.text:
                        try:
                            # Regex ile json içindeki fiyatı cımbızla çek
                            cp_match = re.search(r'"currentPrice"\s*:\s*([\d\.]+)', script.text)
                            if cp_match: current_price = float(cp_match.group(1))
                            
                            op_match = re.search(r'"originalPrice"\s*:\s*([\d\.]+)', script.text)
                            if op_match: original_price = float(op_match.group(1))
                            
                            if current_price > 0: break
                        except: pass

            # --- MANTIK KONTROLLERİ ---
            # Eğer eski fiyat yoksa veya yenisinden düşükse (Hata varsa), eşitle.
            if original_price == 0 or original_price < current_price:
                original_price = current_price

            # Taksit tutarını (örn: 14.90) yanlışlıkla fiyat sanmamak için kontrol
            # Ürün fiyatı genelde 15-20 TL altı olmaz (mendil bile olsa kargo vs 50+ olur)
            # Ama biz yine de etiket bulduysak ona güveniriz.

            # --- 3. İNDİRİM HESAPLAMA ---
            discount_percent = 0
            if original_price > current_price:
                diff = original_price - current_price
                discount_percent = int((diff / original_price) * 100)

            # --- 4. RESİM BULMA ---
            image_url = ""
            # A) Büyük Resim (Carousel içinden)
            img_box = soup.find('img', {'class': 'product-image'})
            if img_box: image_url = img_box.get('src')
            
            # B) Yedek Resim
            if not image_url:
                og_img = soup.find("meta", property="og:image")
                if og_img: image_url = og_img["content"]

            # --- 5. BAŞLIK ---
            title = "Ürün Başlığı"
            h1 = soup.find('h1', {'id': 'product-name'})
            if h1: 
                title = h1.text.strip()
            elif soup.title:
                title = soup.title.text.strip()

            # Verileri Paketle
            product_data = {
                'title': title,
                'current_price': current_price,
                'original_price': original_price,
                'discount_percent': discount_percent,
                'image_url': image_url,
                'product_url': url,
                'platform': 'Hepsiburada',
                'category': 'Genel'
            }
                
        except Exception as e:
            print(f"❌ Hata: {e}")
        finally:
            driver.quit()
            
        return product_data

    def parse_price(self, text):
        if not text: return 0.0
        # "64,99 TL" -> 64.99
        text = str(text).replace('TL', '').strip()
        # 1.250,00 formatı için
        clean = text.replace('.', '').replace(',', '.')
        try:
            return float(clean)
        except:
            return 0.0
