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
        print("🕵️‍♂️ Chrome ve Driver başlatılıyor...")
        
        # Yolları bul (Railway veya Local)
        chrome_path = shutil.which("chromium") or shutil.which("google-chrome") or "/usr/bin/chromium"
        driver_path = shutil.which("chromedriver") or "/usr/bin/chromedriver"
        
        # Ortam değişkenlerini kontrol et
        if not os.path.exists(chrome_path):
             chrome_path = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
        if not os.path.exists(driver_path):
             driver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        
        # Bot Tespitini Aşma Ayarları
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
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
        print(f"🔗 Analiz ediliyor: {url}")
        driver = self.setup_selenium()
        product_data = None
        
        try:
            driver.get(url)
            time.sleep(5) # Sayfanın oturmasını bekle
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Tüm siteler için ORTAK Meta-Tag analizcisi
            product_data = self._parse_universal(soup, url)
                
        except Exception as e:
            print(f"❌ Beklenmedik hata: {e}")
        finally:
            driver.quit()
            
        return product_data

    def _parse_universal(self, soup, url):
        """
        Tüm siteler için geçerli olan Meta-Tag okuyucu.
        Hepsiburada, Trendyol vb. fark etmez, hepsi bu etiketleri kullanır.
        """
        title = "Ürün Başlığı"
        image_url = ""
        current_price = 0.0
        
        # 1. BAŞLIK BULMA (Open Graph > Title Tag)
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title["content"]
        elif soup.title:
            title = soup.title.string

        # Temizlik: " - Hepsiburada" gibi ekleri sil
        title = title.split(" - ")[0].split(" | ")[0].strip()

        # 2. RESİM BULMA (Open Graph > Twitter Card > Link Rel)
        og_image = soup.find("meta", property="og:image")
        if og_image:
            image_url = og_image["content"]
        
        if not image_url:
            link_img = soup.find("link", rel="image_src")
            if link_img: image_url = link_img["href"]

        # 3. FİYAT BULMA (Karmaşık Kısım)
        
        # A) JSON-LD (Google Verisi)
        try:
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                if "price" in script.text:
                    data = json.loads(script.text)
                    if isinstance(data, list): data = data[0]
                    
                    # Farklı JSON yapılarını kontrol et
                    if 'offers' in data:
                        offers = data['offers']
                        if isinstance(offers, list): offers = offers[0]
                        current_price = float(str(offers.get('price', 0)).replace(',', '.'))
                        break
                    if 'price' in data:
                        current_price = float(str(data.get('price', 0)).replace(',', '.'))
                        break
        except:
            pass

        # B) Meta Price (Bazı sitelerde olur)
        if current_price == 0:
            og_price = soup.find("meta", property="product:price:amount")
            if og_price: current_price = float(og_price["content"])

        # C) Regex ile Sayfa Kaynağında Arama (En Son Çare)
        if current_price == 0:
            import re
            # "price": 12345.67 veya "currentPrice": 12345 desenlerini ara
            source = str(soup)
            matches = re.findall(r'"price":\s*(\d+\.?\d*)', source)
            if matches:
                # Bulunan fiyatlardan mantıklı olanı (0 olmayan en büyüğü) al
                prices = [float(p) for p in matches if float(p) > 0]
                if prices: current_price = prices[0]

            # Trendyol/HB özel HTML sınıfları
            if current_price == 0:
                price_box = soup.find(class_=re.compile(r'price|u-price|product-price'))
                if price_box:
                    current_price = self.parse_price(price_box.text)

        platform = "Site"
        if "trendyol" in url: platform = "Trendyol"
        elif "hepsiburada" in url: platform = "Hepsiburada"
        elif "n11" in url: platform = "N11"

        return {
            'title': title,
            'current_price': current_price,
            'original_price': current_price, # İndirim oranı sonra hesaplanır
            'discount_percent': 0,
            'image_url': image_url,
            'product_url': url,
            'platform': platform,
            'category': 'Elektronik'
        }

    def parse_price(self, text):
        if not text: return 0.0
        clean = re.sub(r'[^\d,]', '', text)
        clean = clean.replace(',', '.')
        try:
            return float(clean)
        except:
            return 0.0
