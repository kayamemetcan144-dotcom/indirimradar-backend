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
            time.sleep(5) 
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # --- DEĞİŞKENLER ---
            current_price = 0.0
            original_price = 0.0
            title = "Ürün Başlığı"
            image_url = ""

            # --- 1. ÖZEL HEPSİBURADA SEÇİCİLERİ (EN GÜVENİLİR) ---
            # Hepsiburada genelde fiyatları bu etiketlerle verir, önce bunlara bakacağız.
            
            # A) Güncel Fiyat (İndirimli Hali)
            hb_price = soup.find(['span', 'div'], {'data-test-id': 'price-current-price'})
            if not hb_price:
                 hb_price = soup.find(['span', 'div'], {'id': 'offering-price'})
            
            if hb_price:
                current_price = self.parse_price(hb_price.text)
                print(f"✅ Hepsiburada Etiketi Bulundu: {current_price}")

            # B) Eski Fiyat (Üstü Çizili)
            hb_old_price = soup.find(['span', 'div'], {'data-test-id': 'price-old-price'})
            if hb_old_price:
                original_price = self.parse_price(hb_old_price.text)
            
            # --- 2. YEDEK FİYAT ARAMA (Eğer etiket değiştiyse) ---
            if current_price == 0:
                print("⚠️ Etiket bulunamadı, derin tarama yapılıyor...")
                found_prices = []
                
                # Regex ile tüm sayıları topla
                patterns = [
                    r'"price"\s*:\s*([\d\.]+)', 
                    r'"currentPrice"\s*:\s*([\d\.]+)',
                    r'"amount"\s*:\s*([\d\.]+)',
                    r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*TL'
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, page_source)
                    for m in matches:
                        p = self.parse_price(m)
                        if 20 < p < 500000: # 20 TL altını (Taksit/Kargo) filtrele!
                            found_prices.append(p)

                if found_prices:
                    found_prices = sorted(list(set(found_prices)))
                    # En küçük mantıklı fiyat satış fiyatıdır
                    current_price = found_prices[0]
                    # En büyük fiyat eski fiyattır
                    if len(found_prices) > 1:
                        original_price = found_prices[-1]

            # Eğer eski fiyat bulunamadıysa veya yenisinden küçükse eşitle
            if original_price == 0 or original_price < current_price:
                original_price = current_price

            # --- 3. İNDİRİM HESAPLAMA ---
            discount_percent = 0
            if original_price > current_price:
                diff = original_price - current_price
                discount_percent = int((diff / original_price) * 100)

            # --- 4. RESİM BULMA ---
            og_img = soup.find("meta", property="og:image")
            if og_img: image_url = og_img["content"]
            
            if not image_url:
                matches = re.findall(r'"image"\s*:\s*"([^"]+)"', page_source)
                for m in matches:
                    if "http" in m and ("jpg" in m or "png" in m):
                        image_url = m.replace("\\", "")
                        break
            
            if not image_url:
                 # Slider içindeki ilk büyük resmi al
                 imgs = soup.find_all('img')
                 for img in imgs:
                     src = img.get('src', '')
                     if 'mnresize' in src and '1200' in src: # Büyük resim
                         image_url = src
                         break
                     if 'product' in src and not 'svg' in src:
                         image_url = src
            
            # --- 5. BAŞLIK ---
            if soup.title: title = soup.title.string.strip()
            og_title = soup.find("meta", property="og:title")
            if og_title: title = og_title["content"].strip()
            title = title.split(" Fiyatı")[0].split(" - ")[0]

            # Verileri Paketle
            product_data = {
                'title': title,
                'current_price': current_price,
                'original_price': original_price,
                'discount_percent': discount_percent,
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
        text = str(text).replace('TL', '').strip()
        
        # 1.250,50 -> 1250.50
        if "," in text and "." in text:
             clean = text.replace('.', '').replace(',', '.')
        elif "," in text:
             clean = text.replace(',', '.')
        else:
             clean = text
             
        try:
            return float(clean)
        except:
            return 0.0
