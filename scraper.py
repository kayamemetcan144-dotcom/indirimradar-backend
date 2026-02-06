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
            
            # --- 1. RESİM BULMA ---
            image_url = ""
            og_img = soup.find("meta", property="og:image")
            if og_img: image_url = og_img["content"]
            
            if not image_url:
                matches = re.findall(r'"image"\s*:\s*"([^"]+)"', page_source)
                for m in matches:
                    if "http" in m and ("jpg" in m or "png" in m):
                        image_url = m.replace("\\", "")
                        break

            if not image_url:
                img_tags = soup.find_all('img')
                for img in img_tags:
                    src = img.get('src', '')
                    if src.startswith('http') and ('mnresize' in src or 'product' in src) and not 'svg' in src:
                        image_url = src
                        break

            # --- 2. FİYAT ANALİZİ (GÜNCELLENDİ: MIN/MAX MANTIĞI) ---
            found_prices = []
            
            # A) Regex ile Sayfadaki Tüm Fiyat Benzeri Sayıları Topla
            # "price": 123.45, "amount": 123.45, 123,45 TL gibi desenler
            patterns = [
                r'"price"\s*:\s*([\d\.]+)', 
                r'"currentPrice"\s*:\s*([\d\.]+)',
                r'"originalPrice"\s*:\s*([\d\.]+)',
                r'"amount"\s*:\s*([\d\.]+)',
                r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*TL' # 1.234,56 TL formatı
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, page_source)
                for m in matches:
                    p = self.parse_price(m)
                    # Mantıksız fiyatları ele (örn: 1 TL altı veya tarih gibi sayılar)
                    if 10 < p < 500000: 
                        found_prices.append(p)

            # HTML içindeki data-taglerden de bak
            meta_price = soup.find("meta", property="product:price:amount")
            if meta_price: found_prices.append(float(meta_price["content"]))

            # B) Analiz Yap
            current_price = 0.0
            original_price = 0.0
            
            if found_prices:
                # Tekrar edenleri temizle
                found_prices = sorted(list(set(found_prices)))
                print(f"💰 Bulunan Fiyatlar: {found_prices}")
                
                # En küçük fiyat = Satış Fiyatı (64.99)
                current_price = found_prices[0]
                
                # En büyük fiyat = Eski Fiyat (89.99)
                # Eğer sadece tek fiyat varsa, eski fiyat = yeni fiyat olur
                if len(found_prices) > 1:
                    original_price = found_prices[-1] 
                else:
                    original_price = current_price
            
            # --- 3. İNDİRİM HESAPLAMA ---
            discount_percent = 0
            if original_price > current_price:
                diff = original_price - current_price
                discount_percent = int((diff / original_price) * 100)

            # --- 4. BAŞLIK BULMA ---
            title = "Ürün Başlığı"
            if soup.title: title = soup.title.string.strip()
            og_title = soup.find("meta", property="og:title")
            if og_title: title = og_title["content"].strip()
            
            # Başlık Temizliği
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
        # Metin temizleme: "1.234,50" -> 1234.50
        text = str(text).replace('TL', '').strip()
        
        if "," in text and "." in text:
             # 1.250,50 formatı (Türkçe) -> Noktayı sil, virgülü nokta yap
             clean = text.replace('.', '').replace(',', '.')
        elif "," in text:
             # 1250,50 formatı -> Virgülü nokta yap
             clean = text.replace(',', '.')
        else:
             # 1250 formatı -> Olduğu gibi
             clean = text
             
        try:
            return float(clean)
        except:
            return 0.0
