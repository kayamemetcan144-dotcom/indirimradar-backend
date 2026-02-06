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
        
        # Yol Ayarları
        chrome_bin = shutil.which("chromium") or shutil.which("google-chrome") or "/usr/bin/chromium"
        chromedriver_bin = shutil.which("chromedriver") or "/usr/bin/chromedriver"
        
        if os.environ.get("CHROME_BIN"): chrome_bin = os.environ.get("CHROME_BIN")
        if os.environ.get("CHROMEDRIVER_PATH"): chromedriver_bin = os.environ.get("CHROMEDRIVER_PATH")

        options = Options()
        if self.headless:
            options.add_argument('--headless=new')
            
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        options.binary_location = chrome_bin

        try:
            service = Service(executable_path=chromedriver_bin)
            driver = webdriver.Chrome(service=service, options=options)
            return driver
        except Exception as e:
            print(f"❌ Driver Hatası: {e}")
            raise e

    def scrape_single_product(self, url):
        print(f"🔗 Analiz Ediliyor: {url}")
        driver = None
        
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

            # ======================================================
            # 1. ADIM: JSON-LD (EN GÜVENİLİR KAYNAK - HEM RESİM HEM FİYAT)
            # ======================================================
            scripts = soup.find_all('script', type='application/ld+json')
            for s in scripts:
                try:
                    j = json.loads(s.text)
                    if isinstance(j, list): j = j[0]
                    
                    # Fiyatı Buradan Al
                    if 'offers' in j:
                        offer = j.get('offers', {})
                        if isinstance(offer, list): offer = offer[0]
                        price = float(str(offer.get('price', 0)))
                        if price > 20: # Taksit filtresi
                            data['current_price'] = price
                            print(f"✅ JSON Fiyat Bulundu: {price}")

                    # RESMİ BURADAN AL (Yeni Eklenen Kısım)
                    if 'image' in j:
                        imgs = j['image']
                        if isinstance(imgs, list) and len(imgs) > 0:
                            data['image_url'] = imgs[0] # İlk resim en kalitelisidir
                        elif isinstance(imgs, str):
                            data['image_url'] = imgs
                        print(f"✅ JSON Resim Bulundu: {data['image_url']}")
                    
                    # Başlığı Buradan Al
                    if 'name' in j:
                        data['title'] = j['name']

                    # Eğer hem fiyat hem resim bulduysak çık
                    if data['current_price'] > 0 and data['image_url']:
                        break
                except: pass

            # ======================================================
            # 2. ADIM: EKSİKLERİ TAMAMLA (Yedek Sistemler)
            # ======================================================
            
            # Fiyat hala yoksa Script Regex ile ara
            if data['current_price'] == 0:
                script_prices = re.findall(r'"currentPrice":\s*([\d\.]+)', page_source)
                for p in script_prices:
                    val = float(p)
                    if val > 20: 
                        data['current_price'] = val
                        break

            # Resim hala yoksa OpenGraph veya Regex ile ara
            if not data['image_url']:
                og_img = soup.find("meta", property="og:image")
                if og_img: 
                    data['image_url'] = og_img["content"]
                else:
                    # Regex ile resim ara
                    img_matches = re.findall(r'"image":\s*"([^"]+)"', page_source)
                    for m in img_matches:
                        if "http" in m and ("mnresize" in m or "product" in m):
                            data['image_url'] = m.replace("\\", "")
                            break

            # Başlık hala yoksa
            if data['title'] == 'Ürün Başlığı Bulunamadı':
                if soup.title: data['title'] = soup.title.text.split(" Fiyatı")[0].strip()

            # ======================================================
            # 3. ADIM: HESAPLAMALAR
            # ======================================================
            
            # Eski Fiyatı Bul
            orig_matches = re.findall(r'"originalPrice":\s*([\d\.]+)', page_source)
            valid_orig = [float(x) for x in orig_matches if float(x) > data['current_price']]
            
            if valid_orig:
                data['original_price'] = max(valid_orig)
            else:
                data['original_price'] = data['current_price']

            # İndirim Hesapla
            if data['original_price'] > data['current_price']:
                diff = data['original_price'] - data['current_price']
                data['discount_percent'] = int((diff / data['original_price']) * 100)
                if data['discount_percent'] > 25: data['real_deal_status'] = 'real'

        except Exception as e:
            print(f"❌ Hata: {e}")
        finally:
            if driver: driver.quit()
            
        return data

    def clean_price(self, text):
        if not text: return 0.0
        try:
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
