import requests
from bs4 import BeautifulSoup
import re
import json
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
# Fake UserAgent ekledik (Yoksa standart headers kullanacağız)
try:
    from fake_useragent import UserAgent
except ImportError:
    UserAgent = None

class ProductScraper:
    """
    Web scraping sınıfı - Hem toplu tarama hem de tekil ürün ekleme için güncellendi.
    """
    
    def __init__(self, headless=True):
        self.headless = headless
        self.session = requests.Session()
        # Robot gibi görünmemek için tarayıcı kimliği
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.google.com/'
        }
        self.session.headers.update(self.headers)
    
    def setup_selenium(self):
        """Selenium WebDriver kurulumu - Railway Uyumlu"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        
        # --- KRİTİK AYAR: Railway'deki Chrome'u bul ---
        import os
        # Railway üzerinde Chromium genelde bu yollarda olur, sırayla deneyelim
        chrome_bin = os.popen("which chromium").read().strip() or "/usr/bin/chromium"
        chromedriver_bin = os.popen("which chromedriver").read().strip() or "/usr/bin/chromedriver"

        chrome_options.binary_location = chrome_bin
        
        # WebDriver servisini sistemdeki chromedriver ile başlat
        from selenium.webdriver.chrome.service import Service
        service = Service(executable_path=chromedriver_bin)

        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # WebDriver olduğunu gizle
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
        
    # ==================== YENİ: TEK ÜRÜN ÇEKME (LINK İLE) ====================
    def scrape_single_product(self, url):
        """
        Verilen tek bir ürün linkine gider ve detaylarını çeker.
        Selenium kullanır çünkü Hepsiburada/Trendyol requests'i engeller.
        """
        print(f"🕵️‍♂️ Ürün analizi başlıyor: {url}")
        driver = self.setup_selenium()
        
        product_data = None
        
        try:
            driver.get(url)
            time.sleep(3) # Sayfanın yüklenmesini bekle
            
            # Platforma göre ayrıştır
            if "trendyol.com" in url:
                product_data = self._parse_trendyol_detail(driver, url)
            elif "hepsiburada.com" in url:
                product_data = self._parse_hepsiburada_detail(driver, url)
            elif "n11.com" in url:
                product_data = self._parse_n11_detail(driver, url)
            else:
                # Bilinmeyen site ise genel meta taglardan çekmeyi dene
                product_data = self._parse_generic_detail(driver, url)
                
        except Exception as e:
            print(f"❌ Ürün çekme hatası: {e}")
        finally:
            driver.quit()
            
        return product_data

    # --- Yardımcı Parse Fonksiyonları ---
    
    def _parse_trendyol_detail(self, driver, url):
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        title = soup.find('h1', class_='pr-new-br').text.strip() if soup.find('h1', class_='pr-new-br') else "Başlık Bulunamadı"
        
        price_container = soup.find('span', class_='prc-dsc')
        current_price = self.parse_price(price_container.text) if price_container else 0.0
        
        img_tag = soup.find('img', class_='base-product-image') # Bu değişebilir
        if not img_tag:
             # Alternatif resim bulucu
             img_tag = soup.select_one('.product-slide-container img')
             
        image_url = img_tag['src'] if img_tag else ""
        
        return {
            'title': title,
            'current_price': current_price,
            'original_price': current_price, # İndirimsiz halini bulamazsa aynısını yaz
            'discount_percent': 0,
            'image_url': image_url,
            'product_url': url,
            'platform': 'Trendyol',
            'category': self.detect_category(title)
        }

    def _parse_hepsiburada_detail(self, driver, url):
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Hepsiburada ID ile veri saklar
        title = soup.find('h1', {'id': 'product-name'}).text.strip() if soup.find('h1', {'id': 'product-name'}) else "Ürün"
        
        # Fiyat (Bazen markup değişir)
        price_span = soup.find('span', {'data-bind': "markupText:'currentPriceBeforePoint'"})
        if not price_span:
            # Yeni tasarımda farklı olabilir, meta tagdan deneyelim
            price_content = soup.find('span', content=True, itemprop='price')
            current_price = float(price_content['content']) if price_content else 0.0
        else:
            current_price = self.parse_price(price_span.text)

        # Resim
        img_tag = soup.find('img', class_='product-image')
        if not img_tag:
             img_tag = soup.select_one('#productDetailsCarousel img')
             
        image_url = img_tag['src'] if img_tag else ""

        return {
            'title': title,
            'current_price': current_price,
            'original_price': current_price,
            'discount_percent': 0,
            'image_url': image_url,
            'product_url': url,
            'platform': 'Hepsiburada',
            'category': self.detect_category(title)
        }

    def _parse_n11_detail(self, driver, url):
        # N11 requests ile de çalışabilir ama Selenium garanti
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        title = soup.find('h1', class_='proName').text.strip() if soup.find('h1', class_='proName') else "Ürün"
        
        price_tag = soup.find('div', class_='newPrice')
        current_price = self.parse_price(price_tag.ins.text) if price_tag and price_tag.ins else 0.0
        
        img_tag = soup.find('div', class_='imgObj').find('a')['href'] if soup.find('div', class_='imgObj') else ""
        
        return {
            'title': title,
            'current_price': current_price,
            'original_price': current_price,
            'discount_percent': 0,
            'image_url': img_tag,
            'product_url': url,
            'platform': 'N11',
            'category': self.detect_category(title)
        }

    def _parse_generic_detail(self, driver, url):
        # Bilinmeyen site için Meta Tagları kullan
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        og_title = soup.find("meta", property="og:title")
        title = og_title["content"] if og_title else driver.title
        
        og_image = soup.find("meta", property="og:image")
        image_url = og_image["content"] if og_image else ""
        
        # Fiyat bulmak zordur, 0 döneceğiz, kullanıcı elle girebilir
        return {
            'title': title,
            'current_price': 0.0,
            'original_price': 0.0,
            'discount_percent': 0,
            'image_url': image_url,
            'product_url': url,
            'platform': 'Other',
            'category': 'Diğer'
        }

    # ==================== MEVCUT KATEGORİ SCRAPERLARI (DOKUNMADIM) ====================
    
    def scrape_trendyol_category(self, category_url, max_products=50):
        # (Eski kodun aynısı buraya gelecek, yer kaplamaması için kısaltıyorum)
        # ... Eski scrape_trendyol_category içeriği ...
        return [] # Yer tutucu, sen silme, eski kod kalsın

    # (Diğer fonksiyonlar: parse_price, detect_category vs. aynen kalsın)
    def parse_price(self, price_text):
        if not price_text: return 0.0
        price_text = re.sub(r'[^\d,.]', '', str(price_text))
        price_text = price_text.replace('.', '').replace(',', '.')
        try:
            return float(price_text)
        except:
            return 0.0
    
    def detect_category(self, title):
        title_lower = title.lower()
        if any(w in title_lower for w in ['iphone', 'samsung', 'xiaomi', 'bilgisayar', 'kulaklık']): return 'Elektronik'
        return 'Diğer'

    def calculate_real_deal(self, cp, op, d):
        return 'normal'

    # (Toplu tarama fonksiyonlarını da koru)
