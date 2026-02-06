import requests
from bs4 import BeautifulSoup
import re
import json
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import shutil

class ProductScraper:
    def __init__(self, headless=True):
        self.headless = headless
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7'
        }

    def setup_selenium(self):
        print("🕵️‍♂️ Chrome ve Driver aranıyor...")
        chrome_path = shutil.which("chromium") or shutil.which("google-chrome") or "/usr/bin/chromium"
        driver_path = shutil.which("chromedriver") or "/usr/bin/chromedriver"
        
        # Eğer sistemde bulamazsa (Railway ortam değişkenlerini dene)
        import os
        if not os.path.exists(chrome_path):
             chrome_path = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
        if not os.path.exists(driver_path):
             driver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

        print(f"📍 Kullanılan Chrome: {chrome_path}")

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080') # Tam ekran aç ki öğeler gizlenmesin
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
        print(f"🔗 Linke gidiliyor: {url}")
        driver = self.setup_selenium()
        product_data = None
        
        try:
            driver.get(url)
            time.sleep(5) # Sayfanın tam yüklenmesini bekle
            
            # Sayfa kaynağını al ve BeautifulSoup ile işle
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            if "trendyol.com" in url:
                product_data = self._parse_trendyol_detail(soup, url)
            elif "hepsiburada.com" in url:
                product_data = self._parse_hepsiburada_detail(soup, url)
            else:
                product_data = self._parse_generic_detail(soup, url)
                
        except Exception as e:
            print(f"❌ Beklenmedik hata: {e}")
        finally:
            driver.quit()
            
        return product_data

    # --- HEPSİBURADA (GÜNCELLENDİ: JSON-LD YÖNTEMİ) ---
    def _parse_hepsiburada_detail(self, soup, url):
        print("🛒 Hepsiburada analizi yapılıyor...")
        
        title = "Ürün Başlığı Bulunamadı"
        current_price = 0.0
        original_price = 0.0
        image_url = ""
        
        # 1. YÖNTEM: JSON-LD (En Güvenilir)
        # Hepsiburada ürün bilgilerini sayfanın içinde gizli bir JSON paketinde tutar.
        try:
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    data = json.loads(script.text)
                    # Bazen liste döner, bazen sözlük
                    if isinstance(data, list):
                        data = data[0]
                    
                    if data.get('@type') == 'Product':
                        title = data.get('name', title)
                        image_url = data.get('image', "")
                        
                        offers = data.get('offers', {})
                        price = str(offers.get('price', 0))
                        current_price = float(price.replace(',', '.'))
                        original_price = current_price # Hepsiburada JSON'da eski fiyatı vermeyebilir
                        print("✅ JSON-LD verisi okundu!")
                        break
                except:
                    continue
        except Exception as e:
            print(f"⚠️ JSON okuma hatası: {e}")

        # 2. YÖNTEM: HTML Selector (Yedek Plan)
        # Eğer JSON boş geldiyse veya fiyat 0 ise HTML'den çekmeyi dene
        if current_price == 0:
            print("⚠️ HTML taramasına geçiliyor...")
            
            # Başlık
            h1 = soup.find('h1', {'id': 'product-name'})
            if h1: title = h1.text.strip()
            
            # Fiyat (Çeşitli ihtimaller)
            price_elem = soup.find('span', {'data-test-id': 'price-current-price'}) # Masaüstü
            if not price_elem:
                price_elem = soup.find('div', {'class': 'price-value'}) # Mobil
            
            if price_elem:
                current_price = self.parse_price(price_elem.text)
            
            # Eski Fiyat
            old_price_elem = soup.find('span', {'data-test-id': 'price-old-price'})
            if old_price_elem:
                original_price = self.parse_price(old_price_elem.text)
            else:
                original_price = current_price
            
            # Resim
            if not image_url:
                img = soup.find('img', {'class': 'product-image'})
                if img: image_url = img.get('src')

        # İndirim Oranı Hesapla
        discount = 0
        if original_price > current_price:
            discount = int(((original_price - current_price) / original_price) * 100)

        return {
            'title': title,
            'current_price': current_price,
            'original_price': original_price,
            'discount_percent': discount,
            'image_url': image_url,
            'product_url': url,
            'platform': 'Hepsiburada',
            'category': 'Elektronik' # Otomatik kategori eklenebilir
        }

    # --- TRENDYOL (GÜNCELLENDİ) ---
    def _parse_trendyol_detail(self, soup, url):
        print("🛒 Trendyol analizi yapılıyor...")
        title = "Trendyol Ürünü"
        current_price = 0.0
        image_url = ""
        
        # Başlık
        h1 = soup.find('h1', class_='pr-new-br')
        if h1: title = h1.text.strip()
        
        # Fiyat
        price_span = soup.find('span', class_='prc-dsc')
        if price_span: current_price = self.parse_price(price_span.text)
        
        # Resim
        img_box = soup.find('div', class_='gallery-container')
        if img_box:
            img = img_box.find('img')
            if img: image_url = img.get('src')
            
        return {
            'title': title,
            'current_price': current_price,
            'original_price': current_price,
            'discount_percent': 0,
            'image_url': image_url,
            'product_url': url,
            'platform': 'Trendyol',
            'category': 'Diğer'
        }

    def _parse_generic_detail(self, soup, url):
        # Genel site (Meta taglardan oku)
        title = soup.title.string if soup.title else "Ürün"
        
        og_image = soup.find('meta', property='og:image')
        image_url = og_image['content'] if og_image else ""
        
        return {
            'title': title,
            'current_price': 0.0,
            'original_price': 0.0,
            'discount_percent': 0,
            'image_url': image_url,
            'product_url': url,
            'platform': 'Diğer',
            'category': 'Diğer'
        }

    def parse_price(self, text):
        if not text: return 0.0
        # "12.345,67 TL" formatını "12345.67" float'a çevirir
        clean = re.sub(r'[^\d,]', '', text) # Sadece rakam ve virgül kalsın
        clean = clean.replace(',', '.') # Virgülü noktaya çevir
        try:
            return float(clean)
        except:
            return 0.0
