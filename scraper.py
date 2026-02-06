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
        
        # 1. Chrome ve Driver Yollarını Bul (Railway ve Local Uyumlu)
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
            'platform': 'Site',
            'category': 'Genel',
            'real_deal_status': 'normal'
        }

        # Platform Belirle
        if 'hepsiburada' in url: data['platform'] = 'Hepsiburada'
        elif 'trendyol' in url: data['platform'] = 'Trendyol'
        elif 'n11' in url: data['platform'] = 'N11'

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
                    text_content = s.text
                    # Bazı sitelerde json script içinde gömülü olabilir, temizle
                    if not text_content: continue
                    
                    j = json.loads(text_content)
                    if isinstance(j, list): j = j[0]
                    
                    # Bu bir Ürün mü?
                    if j.get('@type') == 'Product' or 'offers' in j:
                        print("✅ JSON Verisi Bulundu!")
                        
                        # Fiyatı Al
                        if 'offers' in j:
                            offer = j.get('offers', {})
                            if isinstance(offer, list): offer = offer[0]
                            price = float(str(offer.get('price', 0)))
                            if price > 15: # Taksit filtresi
                                data['current_price'] = price
                        
                        # Resmi Al
                        if 'image' in j:
                            imgs = j['image']
                            if isinstance(imgs, list) and len(imgs) > 0:
                                data['image_url'] = imgs[0]
                            elif isinstance(imgs, str):
                                data['image_url'] = imgs
                        
                        # Başlığı Al
                        if 'name' in j:
                            data['title'] = j['name']
                            
                        # Eğer verileri bulduysak döngüden çık
                        if data['current_price'] > 0:
                            break
                except: pass

            # ======================================================
            # 2. ADIM: HİBRİT FİYAT TARAMASI (Eğer JSON Başarısızsa)
            # ======================================================
            if data['current_price'] == 0:
                print("⚠️ JSON Fiyat bulunamadı, Script ve HTML taranıyor...")
                prices = []
                
                # A) Script Değişkenleri (Regex)
                # "currentPrice": 123.45 veya "price": 123.45 desenlerini ara
                script_prices = re.findall(r'"currentPrice":\s*([\d\.]+)', page_source)
                if not script_prices:
                    script_prices = re.findall(r'"price":\s*([\d\.]+)', page_source)
                    
                for p in script_prices:
                    val = float(p)
                    if val > 15: prices.append(val)

                # B) HTML Etiketleri (Hepsiburada/Trendyol Özel)
                # Hepsiburada
                hb_price = soup.find(['span', 'div'], {'data-test-id': 'price-current-price'})
                if hb_price: 
                    val = self.clean_price(hb_price.text)
                    if val > 15: prices.append(val)
                
                # Trendyol
                ty_price = soup.find('span', class_='prc-dsc')
                if ty_price:
                    val = self.clean_price(ty_price.text)
                    if val > 15: prices.append(val)

                # En mantıklı fiyatı seç (En düşük geçerli fiyat satış fiyatıdır)
                if prices:
                    data['current_price'] = min(prices)
                    print(f"💰 Bulunan Fiyat: {data['current_price']} TL")

            # ======================================================
            # 3. ADIM: RESİM TAMAMLAMA (Eğer JSON Başarısızsa)
            # ======================================================
            if not data['image_url']:
                # A) OpenGraph (Facebook)
                og_img = soup.find("meta", property="og:image")
                if og_img: data['image_url'] = og_img["content"]
                
                # B) Script İçindeki Büyük Resimler
                if not data['image_url']:
                    img_matches = re.findall(r'"image":\s*"([^"]+)"', page_source)
                    for m in img_matches:
                        if "http" in m and ("mnresize" in m or "product" in m or "cdn" in m):
                            data['image_url'] = m.replace("\\", "")
                            break
                
                # C) HTML İlk Resim
                if not data['image_url']:
                    img = soup.find('img', {'class': 'product-image'}) # HB
                    if not img: img = soup.find('img', {'loading': 'lazy'}) # Genel
                    if img: data['image_url'] = img.get('src')

            # ======================================================
            # 4. ADIM: ESKİ FİYAT VE İNDİRİM
            # ======================================================
            
            # Eski Fiyatı Bul (Regex ile 'originalPrice' ara)
            orig_matches = re.findall(r'"originalPrice":\s*([\d\.]+)', page_source)
            valid_orig = [float(x) for x in orig_matches if float(x) > data['current_price']]
            
            if valid_orig:
                data['original_price'] = max(valid_orig)
            elif data['original_price'] == 0:
                # HTML'den bak
                old_tag = soup.find(['span', 'div'], {'data-test-id': 'price-old-price'}) # HB
                if not old_tag: old_tag = soup.find('span', class_='prc-org') # Trendyol
                
                if old_tag:
                    op = self.clean_price(old_tag.text)
                    if op > data['current_price']: data['original_price'] = op
            
            # Hala yoksa eşitle
            if data['original_price'] == 0: data['original_price'] = data['current_price']

            # İndirim Yüzdesi
            if data['original_price'] > data['current_price']:
                diff = data['original_price'] - data['current_price']
                data['discount_percent'] = int((diff / data['original_price']) * 100)
                if data['discount_percent'] > 20: data['real_deal_status'] = 'real'

            # Başlık Temizliği
            if not data['title'] or data['title'] == 'Ürün Başlığı Bulunamadı':
                if soup.title: data['title'] = soup.title.text.strip()
            
            data['title'] = data['title'].split(" Fiyatı")[0].split(" | ")[0].strip()

        except Exception as e:
            print(f"❌ Tarama Hatası: {e}")
        finally:
            if driver: driver.quit()
            
        return data

    def clean_price(self, text):
        """Fiyat metnini temizler: 1.250,90 TL -> 1250.9"""
        if not text: return 0.0
        try:
            text = str(text).replace('TL', '').replace('tl', '').strip()
            if "," in text and "." in text: 
                clean = text.replace('.', '').replace(',', '.')
            elif "," in text: 
                clean = text.replace(',', '.')
            else:
                clean = text
            return float(clean)
        except:
            return 0.0

    # Eski metotların yerine boş/geçici metotlar (Hata vermemesi için)
    def scrape_trendyol_category(self, url, max_products=10): return []
    def scrape_hepsiburada_category(self, url, max_products=10): return []
    def scrape_n11_category(self, url, max_products=10): return []
    def scrape_all_platforms(self): return []
