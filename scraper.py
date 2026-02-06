"""
İndirimRadar Web Scraper
Trendyol, Hepsiburada ve N11 platformlarından ürün verilerini çeker
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import random
from datetime import datetime

# ==================== CONFIGURATION ====================

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
]

# Frontend ile uyumlu kategoriler
CATEGORIES = {
    'Elektronik': [
        'telefon', 'laptop', 'tv', 'tablet', 'kulaklik', 
        'akilli-saat', 'bilgisayar', 'kamera'
    ],
    'Moda': [
        'ayakkabi', 'tisort', 'elbise', 'pantolon', 'ceket',
        'gomlek', 'spor-ayakkabi', 'sneaker'
    ],
    'Ev': [
        'mobilya', 'dekorasyon', 'mutfak', 'banyo', 'yatak',
        'halı', 'perde', 'aydınlatma'
    ],
    'Süpermarket': [
        'gida', 'icecek', 'atistirmalik', 'kahve', 'cay',
        'deterjan', 'temizlik', 'kisisel-bakim'
    ],
    'Kozmetik': [
        'parfum', 'makyaj', 'cilt-bakimi', 'sac-bakimi',
        'vucut-bakimi', 'guzellik'
    ]
}

# Platform URL'leri
PLATFORMS = {
    'Trendyol': {
        'base_url': 'https://www.trendyol.com',
        'search_url': 'https://www.trendyol.com/sr'
    },
    'Hepsiburada': {
        'base_url': 'https://www.hepsiburada.com',
        'search_url': 'https://www.hepsiburada.com/ara'
    },
    'N11': {
        'base_url': 'https://www.n11.com',
        'search_url': 'https://www.n11.com/arama'
    }
}

# ==================== HELPER FUNCTIONS ====================

def get_random_headers():
    """Random user agent ile headers oluştur"""
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/json',
        'Accept-Language': 'tr-TR,tr;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }

def clean_price(price_text):
    """Fiyat string'ini float'a çevir"""
    try:
        # Remove currency symbols and spaces
        cleaned = price_text.replace('TL', '').replace('₺', '').replace('.', '').replace(',', '.').strip()
        return float(cleaned)
    except:
        return 0.0

def calculate_discount(original, current):
    """İndirim yüzdesini hesapla"""
    try:
        if original > 0 and current > 0:
            return round(((original - current) / original) * 100)
        return 0
    except:
        return 0

def is_real_deal(original_price, current_price, discount_percent):
    """Gerçek indirim mi kontrol et"""
    # Basit kontroller
    if discount_percent >= 20:  # %20'den fazla indirim
        return 'real'
    elif discount_percent >= 10:
        return 'normal'
    else:
        return 'normal'

def get_category_from_keyword(keyword):
    """Anahtar kelimeden kategori bul"""
    keyword_lower = keyword.lower()
    
    # Kategori eşleştirmesi
    electronics_keywords = ['telefon', 'laptop', 'tv', 'bilgisayar', 'tablet', 'kulaklik', 'kamera']
    fashion_keywords = ['ayakkabi', 'elbise', 'pantolon', 'ceket', 'gomlek', 'tişört']
    home_keywords = ['mobilya', 'dekorasyon', 'mutfak', 'yatak', 'halı']
    supermarket_keywords = ['gida', 'icecek', 'kahve', 'cay', 'deterjan']
    cosmetic_keywords = ['parfum', 'makyaj', 'cilt', 'sac', 'guzellik']
    
    if any(k in keyword_lower for k in electronics_keywords):
        return 'Elektronik'
    elif any(k in keyword_lower for k in fashion_keywords):
        return 'Moda'
    elif any(k in keyword_lower for k in home_keywords):
        return 'Ev'
    elif any(k in keyword_lower for k in supermarket_keywords):
        return 'Süpermarket'
    elif any(k in keyword_lower for k in cosmetic_keywords):
        return 'Kozmetik'
    else:
        return 'Elektronik'  # Default

# ==================== TRENDYOL SCRAPER ====================

def scrape_trendyol(keyword, max_products=10):
    """Trendyol'dan ürün çek"""
    products = []
    
    try:
        # API endpoint (Trendyol uses public API)
        url = f'https://public.trendyol.com/discovery-web-searchgw-service/v2/api/infinite-scroll/{keyword}?pi=1&culture=tr-TR&userGenderId=1&pId=0'
        
        headers = get_random_headers()
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get('result', {}).get('products', [])
            
            for item in results[:max_products]:
                try:
                    # Extract product data
                    current_price = item.get('price', {}).get('sellingPrice', 0)
                    original_price = item.get('price', {}).get('originalPrice', current_price)
                    
                    # Skip if no price
                    if current_price == 0:
                        continue
                    
                    discount = calculate_discount(original_price, current_price)
                    
                    product = {
                        'title': item.get('name', ''),
                        'platform': 'Trendyol',
                        'category': get_category_from_keyword(keyword),
                        'current_price': current_price,
                        'original_price': original_price,
                        'discount_percent': discount,
                        'image_url': f"https://cdn.dsmcdn.com{item.get('imageUrl', '')}",
                        'product_url': f"https://www.trendyol.com{item.get('url', '')}",
                        'real_deal_status': is_real_deal(original_price, current_price, discount)
                    }
                    
                    products.append(product)
                
                except Exception as e:
                    print(f"Error parsing Trendyol product: {e}")
                    continue
        
        print(f"✅ Trendyol: {len(products)} ürün çekildi")
    
    except Exception as e:
        print(f"❌ Trendyol scraping error: {e}")
    
    return products

# ==================== HEPSIBURADA SCRAPER ====================

def scrape_hepsiburada(keyword, max_products=10):
    """Hepsiburada'dan ürün çek (Mock data - gerçek scraping için Selenium gerekir)"""
    products = []
    
    try:
        # Hepsiburada için mock data
        # Gerçek production'da Selenium veya API kullanılmalı
        
        print("ℹ️ Hepsiburada: Mock data kullanılıyor")
        
        # Sample mock products
        mock_products = [
            {
                'title': f'{keyword} - Premium Model',
                'platform': 'Hepsiburada',
                'category': get_category_from_keyword(keyword),
                'current_price': 3999.0,
                'original_price': 5999.0,
                'discount_percent': 33,
                'image_url': 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80',
                'product_url': 'https://www.hepsiburada.com',
                'real_deal_status': 'real'
            }
        ]
        
        products = mock_products[:max_products]
        print(f"✅ Hepsiburada: {len(products)} ürün eklendi (mock)")
    
    except Exception as e:
        print(f"❌ Hepsiburada error: {e}")
    
    return products

# ==================== N11 SCRAPER ====================

def scrape_n11(keyword, max_products=10):
    """N11'den ürün çek (Mock data)"""
    products = []
    
    try:
        print("ℹ️ N11: Mock data kullanılıyor")
        
        # Sample mock products
        mock_products = [
            {
                'title': f'{keyword} - Özel Fırsat',
                'platform': 'N11',
                'category': get_category_from_keyword(keyword),
                'current_price': 2499.0,
                'original_price': 3999.0,
                'discount_percent': 38,
                'image_url': 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&q=80',
                'product_url': 'https://www.n11.com',
                'real_deal_status': 'real'
            }
        ]
        
        products = mock_products[:max_products]
        print(f"✅ N11: {len(products)} ürün eklendi (mock)")
    
    except Exception as e:
        print(f"❌ N11 error: {e}")
    
    return products

# ==================== MAIN SCRAPER ====================

def scrape_all_platforms(keyword, max_per_platform=5):
    """Tüm platformlardan ürün çek"""
    all_products = []
    
    print(f"\n🔍 Scraping başlatıldı: '{keyword}'")
    print("=" * 50)
    
    # Trendyol
    time.sleep(random.uniform(1, 2))
    trendyol_products = scrape_trendyol(keyword, max_per_platform)
    all_products.extend(trendyol_products)
    
    # Hepsiburada
    time.sleep(random.uniform(1, 2))
    hepsiburada_products = scrape_hepsiburada(keyword, max_per_platform)
    all_products.extend(hepsiburada_products)
    
    # N11
    time.sleep(random.uniform(1, 2))
    n11_products = scrape_n11(keyword, max_per_platform)
    all_products.extend(n11_products)
    
    print("=" * 50)
    print(f"✅ Toplam {len(all_products)} ürün çekildi\n")
    
    return all_products

def scrape_by_category(category_name, max_per_keyword=3):
    """Kategori bazlı scraping"""
    all_products = []
    
    if category_name not in CATEGORIES:
        print(f"❌ Kategori bulunamadı: {category_name}")
        return []
    
    keywords = CATEGORIES[category_name]
    
    print(f"\n📦 Kategori: {category_name}")
    print(f"🔑 Anahtar kelimeler: {', '.join(keywords)}")
    
    for keyword in keywords[:3]:  # İlk 3 keyword
        products = scrape_all_platforms(keyword, max_per_keyword)
        all_products.extend(products)
        time.sleep(random.uniform(2, 4))  # Rate limiting
    
    return all_products

# ==================== DATABASE INTEGRATION ====================

def save_to_database(products):
    """Ürünleri database'e kaydet"""
    try:
        import sys
        sys.path.append('.')
        from app import app, db, Product, PriceHistory
        
        with app.app_context():
            saved_count = 0
            
            for product_data in products:
                try:
                    # Check if product exists
                    existing = Product.query.filter_by(
                        title=product_data['title'],
                        platform=product_data['platform']
                    ).first()
                    
                    if existing:
                        # Update existing product
                        existing.current_price = product_data['current_price']
                        existing.original_price = product_data['original_price']
                        existing.discount_percent = product_data['discount_percent']
                        existing.real_deal_status = product_data['real_deal_status']
                        existing.updated_at = datetime.utcnow()
                        
                        # Add price history
                        history = PriceHistory(
                            product_id=existing.id,
                            price=product_data['current_price']
                        )
                        db.session.add(history)
                    else:
                        # Create new product
                        new_product = Product(**product_data)
                        db.session.add(new_product)
                        db.session.flush()
                        
                        # Add price history
                        history = PriceHistory(
                            product_id=new_product.id,
                            price=product_data['current_price']
                        )
                        db.session.add(history)
                    
                    saved_count += 1
                
                except Exception as e:
                    print(f"Error saving product: {e}")
                    continue
            
            db.session.commit()
            print(f"✅ {saved_count} ürün database'e kaydedildi")
            
    except Exception as e:
        print(f"❌ Database save error: {e}")

# ==================== COMMAND LINE INTERFACE ====================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='İndirimRadar Web Scraper')
    parser.add_argument('--keyword', type=str, help='Aranacak kelime')
    parser.add_argument('--category', type=str, choices=list(CATEGORIES.keys()), help='Kategori')
    parser.add_argument('--save', action='store_true', help='Database\'e kaydet')
    
    args = parser.parse_args()
    
    products = []
    
    if args.keyword:
        products = scrape_all_platforms(args.keyword)
    elif args.category:
        products = scrape_by_category(args.category)
    else:
        # Default: Tüm kategorilerden sample
        print("\n🚀 Tüm kategorilerden sample ürünler çekiliyor...")
        for category in list(CATEGORIES.keys())[:2]:  # İlk 2 kategori
            category_products = scrape_by_category(category, max_per_keyword=2)
            products.extend(category_products)
    
    # Results
    if products:
        print(f"\n📊 SONUÇLAR:")
        print(f"Toplam ürün: {len(products)}")
        print(f"Ortalama indirim: {sum(p['discount_percent'] for p in products) / len(products):.1f}%")
        
        # Save to database
        if args.save:
            save_to_database(products)
        else:
            print("\nℹ️ Database'e kaydetmek için --save flag'i kullanın")
            
            # Save to JSON file
            output_file = f'scraped_products_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(products, f, ensure_ascii=False, indent=2)
            print(f"💾 Ürünler kaydedildi: {output_file}")
    else:
        print("❌ Hiç ürün bulunamadı")
