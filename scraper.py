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
        
        # Yol Ayarları (Railway ve Local uyumlu)
        chrome_path = shutil.which("chromium") or shutil.which("google-chrome") or "/usr/bin/chromium"
        driver_path = shutil.which("chromedriver") or "/usr/bin/chromedriver"
        
        # Ortam değişkenlerinden kontrol
        if not os.path.exists(chrome_path): 
            chrome_path = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
        if not os.path.exists(driver_path): 
            driver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

        # Chrome Ayarları
        options = Options()
        if self.headless:
            options.add_argument('--headless')
        
        # Bot Tespitini Engelleyen Kritik Ayarlar
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        options.binary_location = chrome_path

        try:
            service = Service(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=options)
            return driver
        except Exception as e:
            print(f"❌ Driver Başlatma Hatası: {str(e)}")
            raise e

    def scrape_single_product(self, url):
        print(f"🔗 Analiz Ediliyor: {url}")
        driver = self.setup_selenium()
        
        # Boş veri şablonu
        data = {
            'title': '',
            'current_price': 0.0,
            'original_price': 0.0,
            'discount_percent': 0,
            'image_url': '',
            'product_url': url,
            'platform': 'Hepsiburada' if 'hepsiburada' in url else 'Diğer',
            'category': 'Genel'
        }

        try:
            driver.get(url)
            # Sayfanın tam yüklenmesi için bekle
            time.sleep(5)
            
            # Kaynak kodunu al
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')

            # ======================================================
            # ADIM 1: FİYAT BULMA (En Kritik Nokta)
            # ======================================================
            prices = []

            # Yöntem A: Script içindeki net değişkenleri ara (En güvenilir)
            # "currentPrice": 64.99 gibi yapıları arar
            script_matches = re.findall(r'"currentPrice":\s*([\d\.]+)', page_source)
            if not script_matches:
                script_matches = re.findall(r'"price":\s*([\d\.]+)', page_source)
            
            for p in script_matches:
                val = float(p)
                if val > 20: prices.append(val) # 20 TL altı taksitleri ele

            # Yöntem B: JSON-LD Verisi
            scripts = soup.find_all('script', type='application/ld+json')
            for s in scripts:
                if 'offers' in s.text:
                    try:
                        j = json.loads(s.text)
                        if isinstance(j, list): j = j[0]
                        offer = j.get('offers', {})
                        if isinstance(offer, list): offer = offer[0]
                        price = float(str(offer.get('price', 0)))
                        if price > 20: prices.append(price)
                    except: pass

            # Yöntem C: HTML Etiketleri (Yedek)
            # Hepsiburada'nın meşhur "data-test-id" etiketleri
            try:
                price_tag = soup.find(['span', 'div'], {'data-test-id': 'price-current-price'})
                if price_tag:
                    p = self.clean_price(price_tag.text)
                    if p > 0: prices.append(p)
            except: pass

            # Fiyat Kararı Verme
            if prices:
                # Bulunan en mantıklı (20 TL üstü) en düşük fiyat satış fiyatıdır.
                data['current_price'] = min(prices)
                print(f"💰 Tespit Edilen Fiyat: {data['current_price']}")

            # ======================================================
            # ADIM 2: ESKİ FİYAT BULMA
            # ======================================================
            old_prices = []
            
            # Script'te "originalPrice" ara
            orig_matches = re.findall(r'"originalPrice":\s*([\d\.]+)', page_source)
            for p in orig_matches: old_prices.append(float(p))

            # HTML'de üstü çizili ara
            old_tag = soup.find(['span', 'div'], {'data-test-id': 'price-old-price'})
            if old_tag:
                p = self.clean_price(old_tag.text)
                if p > data['current_price']: old_prices.append(p)

            if old_prices:
                data['original_price'] = max(old_prices)
            else:
                data['original_price'] = data['current_price']

            # ======================================================
            # ADIM 3: RESİM VE BAŞLIK
            # ======================================================
            
            # Başlık
            if soup.title: data['title'] = soup.title.text.strip().split(" Fiyatı")[0]
            og_title = soup.find("meta", property="og:title")
            if og_title: data['title'] = og_title["content"].split(" Fiyatı")[0]

            # Resim (Öncelik sırasına göre)
            # 1. OpenGraph
            og_img = soup.find("meta", property="og:image")
            if og_img: data['image_url'] = og_img["content"]
            
            # 2. Script içindeki büyük resim
            if not data['image_url']:
                img_matches = re.findall(r'"image":\s*"([^"]+)"', page_source)
                for m in img_matches:
                    if "http" in m and "mnresize" in m:
                        data['image_url'] = m.replace("\\", "")
                        break
            
            # 3. HTML içindeki ilk ürün resmi
            if not data['image_url']:
                img = soup.find('img', {'class': 'product-image'})
                if img: data['image_url'] = img.get('src')

            # ======================================================
            # ADIM 4: SON HESAPLAMALAR
            # ======================================================
            
            # Eğer eski fiyat < yeni fiyat ise (Hata varsa), eşitle
            if data['original_price'] < data['current_price']:
                data['original_price'] = data['current_price']
            
            # İndirim Yüzdesi
            if data['original_price'] > data['current_price']:
                diff = data['original_price'] - data['current_price']
                data['discount_percent'] = int((diff / data['original_price']) * 100)

            # Başlık kontrolü (Hala boşsa)
            if not data['title']: data['title'] = "Ürün Başlığı Alınamadı"

        except Exception as e:
            print(f"❌ Kritik Hata: {e}")
            # Hata olsa bile boş veri dön ki sunucu çökmesin
        finally:
            driver.quit()
        
        return data

    def clean_price(self, text):
        """Metin içindeki fiyatı temizler: '1.250,90 TL' -> 1250.9"""
        if not text: return 0.0
        try:
            # Sadece sayı, nokta ve virgülü bırak
            text = str(text).replace('TL', '').strip()
            if "," in text and "." in text: # 1.250,00 formatı
                clean = text.replace('.', '').replace(',', '.')
            elif "," in text: # 1250,00 formatı
                clean = text.replace(',', '.')
            else:
                clean = text
            return float(clean)
        except:
            return 0.0
