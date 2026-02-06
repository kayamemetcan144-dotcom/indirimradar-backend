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
        
        # Varsayılan Değerler
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
            time.sleep(5) # Sayfanın tam yüklenmesi için bekle
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # === YÖNTEM 1: JSON-LD (Google Verisi - En Güvenilir) ===
            # Sayfanın arkasındaki gizli kimlik kartını okuyoruz.
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    data = json.loads(script.text)
                    if isinstance(data, list): data = data[0] # Bazen liste içinde gelir
                    
                    # Eğer bu bir Ürün verisiyse
                    if data.get('@type') == 'Product':
                        print("✅ Resmi Ürün Verisi (JSON-LD) Bulundu!")
                        
                        # 1. Başlık
                        if 'name' in data: 
                            product_data['title'] = data['name']
                        
                        # 2. Resim (Liste veya tek link olabilir)
                        if 'image' in data:
                            imgs = data['image']
                            if isinstance(imgs, list) and len(imgs) > 0:
                                product_data['image_url'] = imgs[0]
                            elif isinstance(imgs, str):
                                product_data['image_url'] = imgs

                        # 3. Fiyat (Offers içinde olur)
                        if 'offers' in data:
                            offer = data['offers']
                            if isinstance(offer, list): offer = offer[0] # İlk teklifi al
                            
                            price = str(offer.get('price', 0))
                            product_data['current_price'] = float(price)
                            # JSON-LD genelde sadece satış fiyatını verir, eski fiyatı vermez.
                            # O yüzden şimdilik eski fiyat = yeni fiyat yapalım, aşağıda düzelteceğiz.
                            product_data['original_price'] = product_data['current_price']
                        
                        break # Veriyi bulduk, döngüden çık
                except:
                    continue

            # === YÖNTEM 2: EKSİK VERİLERİ TAMAMLAMA (HTML'den) ===
            
            # Eğer resim JSON'dan gelmediyse HTML'den al
            if not product_data['image_url']:
                img = soup.find('img', {'class': 'product-image'})
                if img: product_data['image_url'] = img.get('src')
            
            # Eğer Başlık gelmediyse
            if product_data['title'] == 'Ürün Başlığı Bulunamadı':
                h1 = soup.find('h1', {'id': 'product-name'})
                if h1: product_data['title'] = h1.text.strip()

            # === YÖNTEM 3: ESKİ FİYAT VE İNDİRİM (HTML'den Kontrol) ===
            # JSON-LD sadece "64.99" der. "89.99" demez. Onu HTML'den bulacağız.
            
            # HTML'deki "Eski Fiyat" etiketine bak
            old_price_html = soup.find(['div', 'span', 'del'], {'data-test-id': 'price-old-price'})
            
            if old_price_html:
                old_val = self.parse_price(old_price_html.text)
                if old_val > product_data['current_price']:
                    product_data['original_price'] = old_val
                    print(f"✅ Eski Fiyat HTML'den Bulundu: {old_val}")

            # İndirim Hesapla
            if product_data['original_price'] > product_data['current_price']:
                diff = product_data['original_price'] - product_data['current_price']
                product_data['discount_percent'] = int((diff / product_data['original_price']) * 100)

            # Temizlik
            product_data['title'] = product_data['title'].strip()

        except Exception as e:
            print(f"❌ Hata oluştu: {e}")
        finally:
            driver.quit()
            
        return product_data

    def parse_price(self, text):
        if not text: return 0.0
        # "89,99 TL" -> 89.99
        text = str(text).replace('TL', '').replace('tl', '').strip()
        # 1.250,50 -> 1250.50
        clean = text.replace('.', '').replace(',', '.')
        try:
            return float(clean)
        except:
            return 0.0
