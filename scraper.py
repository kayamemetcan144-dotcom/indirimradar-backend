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
        print("🕵️‍♂️ Tarayıcı Başlatılıyor...")
        
        # 1. Chrome ve Driver Yollarını Bul
        chrome_bin = shutil.which("chromium") or shutil.which("google-chrome") or "/usr/bin/chromium"
        chromedriver_bin = shutil.which("chromedriver") or "/usr/bin/chromedriver"
        
        # Ortam Değişkeni Varsa Onu Kullan
        if os.environ.get("CHROME_BIN"): chrome_bin = os.environ.get("CHROME_BIN")
        if os.environ.get("CHROMEDRIVER_PATH"): chromedriver_bin = os.environ.get("CHROMEDRIVER_PATH")

        # 2. Kritik Chrome Ayarları (Çökmeyi Önler)
        options = Options()
        if self.headless:
            options.add_argument('--headless=new') # Yeni nesil headless modu
            
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage') # Hafıza hatasını önler
        options.add_argument('--disable-gpu')
        options.add_argument('--remote-debugging-pipe') # DevToolsActivePort hatasını çözer
        options.add_argument('--disable-blink-features=AutomationControlled') # Bot tespitini zorlaştırır
        options.add_argument('--window-size=1920,1080')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        
        options.binary_location = chrome_bin

        try:
            service = Service(executable_path=chromedriver_bin)
            driver = webdriver.Chrome(service=service, options=options)
            return driver
        except Exception as e:
            print(f"❌ Kritik Hata - Driver Başlatılamadı: {e}")
            raise e

    def scrape_single_product(self, url):
        print(f"🔗 Link Analiz Ediliyor: {url}")
        driver = None
        
        # Boş Veri Şablonu
        data = {
            'title': 'Ürün Başlığı Bulunamadı',
            'current_price': 0.0,
            'original_price': 0.0,
            'discount_percent': 0,
            'image_url': '',
            'product_url': url,
            'platform': 'Hepsiburada' if 'hepsiburada' in url else 'Diğer',
            'category': 'Genel',
            'real_deal_status': 'normal'
        }

        try:
            driver = self.setup_selenium()
            driver.get(url)
            time.sleep(5) # Sayfanın tam yüklenmesini bekle
            
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')

            # === 1. FİYAT BULMA (HİBRİT YÖNTEM) ===
            prices = []
            
            # A) Script Değişkenlerinden (En Güvenilir - Taksit Fiyatını Elmek İçin)
            # Sayfa kodunda "currentPrice": 123.45 şeklindeki veriyi arar
            script_prices = re.findall(r'"currentPrice":\s*([\d\.]+)', page_source)
            if not script_prices:
                script_prices = re.findall(r'"price":\s*([\d\.]+)', page_source)
                
            for p in script_prices:
                val = float(p)
                if val > 20: prices.append(val) # 20 TL altı taksitleri yoksay

            # B) JSON-LD Verisinden (Google Verisi)
            if not prices:
                scripts = soup.find_all('script', type='application/ld+json')
                for s in scripts:
                    if 'offers' in s.text:
                        try:
                            j = json.loads(s.text)
                            if isinstance(j, list): j = j[0]
                            offer = j.get('offers', {})
                            if isinstance(offer, list): offer = offer[0]
                            p = float(str(offer.get('price', 0)))
                            if p > 20: prices.append(p)
                        except: pass
            
            # C) HTML Etiketlerinden (Yedek)
            if not prices:
                price_tag = soup.find(['span', 'div'], {'data-test-id': 'price-current-price'})
                if price_tag:
                    p = self.clean_price(price_tag.text)
                    if p > 20: prices.append(p)

            # Fiyatı Belirle
            if prices:
                data['current_price'] = min(prices)
                print(f"💰 Bulunan Fiyat: {data['current_price']} TL")

            # === 2. ESKİ FİYAT BULMA ===
            # "originalPrice": 150.00 verisini ara
            orig_matches = re.findall(r'"originalPrice":\s*([\d\.]+)', page_source)
            valid_orig = [float(x) for x in orig_matches if float(x) > data['current_price']]
            
            if valid_orig:
                data['original_price'] = max(valid_orig)
            else:
                # HTML'den bak
                old_tag = soup.find(['span', 'div'], {'data-test-id': 'price-old-price'})
                if old_tag:
                    op = self.clean_price(old_tag.text)
                    if op > data['current_price']: data['original_price'] = op
            
            # Hala yoksa, eski fiyat = yeni fiyat
            if data['original_price'] == 0: data['original_price'] = data['current_price']

            # === 3. RESİM BULMA ===
            # A) Facebook (OpenGraph) Resmi - Genelde en iyisidir
            og_img = soup.find("meta", property="og:image")
            if og_img: data['image_url'] = og_img["content"]
            
            # B) Script içindeki büyük resim
            if not data['image_url']:
                img_matches = re.findall(r'"image":\s*"([^"]+)"', page_source)
                for m in img_matches:
                    if "http" in m and "mnresize" in m:
                        data['image_url'] = m.replace("\\", "")
                        break
            
            # C) HTML Resim etiketi
            if not data['image_url']:
                img = soup.find('img', {'class': 'product-image'})
                if img: data['image_url'] = img.get('src')

            # === 4. BAŞLIK ===
            if soup.title: data['title'] = soup.title.text.split(" Fiyatı")[0].strip()
            
            # === 5. İNDİRİM HESAPLA ===
            if data['original_price'] > data['current_price']:
                diff = data['original_price'] - data['current_price']
                data['discount_percent'] = int((diff / data['original_price']) * 100)
                if data['discount_percent'] > 25: data['real_deal_status'] = 'real'

        except Exception as e:
            print(f"❌ Tarama Hatası: {e}")
        finally:
            if driver: driver.quit()
            
        return data

    def clean_price(self, text):
        if not text: return 0.0
        try:
            # "1.250,90 TL" -> 1250.9
            text = str(text).replace('TL', '').strip()
            if "," in text and "." in text: 
                clean = text.replace('.', '').replace(',', '.')
            elif "," in text: 
                clean = text.replace(',', '.')
            else:
                clean = text
            return float(clean)
        except:
            return 0.0
