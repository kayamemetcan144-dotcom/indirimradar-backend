from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os
from scraper import ProductScraper 

app = Flask(__name__)

# Ayarlar
allowed_origins = os.getenv('ALLOWED_ORIGINS', '*').split(',')
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')
database_url = os.getenv('DATABASE_URL', 'sqlite:///indirimradar.db')
if database_url.startswith('postgres://'): database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELLER ---
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    platform = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    current_price = db.Column(db.Float, nullable=False)
    original_price = db.Column(db.Float, nullable=False)
    discount_percent = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(1000), nullable=False)
    product_url = db.Column(db.String(1000), nullable=False)
    real_deal_status = db.Column(db.String(20), default='normal')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    # İlişkiler (Gerekirse)
    # favorites = ...

# --- ROTALAR ---

@app.route('/api/products', methods=['GET'])
def get_products():
    page = int(request.args.get('page', 1))
    products = Product.query.order_by(Product.id.desc()).paginate(page=page, per_page=20, error_out=False)
    return jsonify({
        'products': [{
            'id': p.id, 'title': p.title, 'platform': p.platform,
            'current_price': p.current_price, 'original_price': p.original_price,
            'discount_percent': p.discount_percent, 'image_url': p.image_url,
            'url': p.product_url, 'real_deal_status': p.real_deal_status
        } for p in products.items]
    })

# Manuel Fiyat Destekleyen Ekleme Fonksiyonu
@app.route('/api/products', methods=['POST'])
def add_product_via_link():
    data = request.get_json()
    url = data.get('url')
    manual_price = data.get('manual_price')        
    manual_old_price = data.get('manual_old_price')
    
    if not url: return jsonify({'message': 'URL gerekli'}), 400

    existing = Product.query.filter_by(product_url=url).first()
    if existing: return jsonify({'message': 'Bu ürün zaten takip ediliyor', 'id': existing.id}), 200

    try:
        # Bot veriyi çekmeye çalışır (Resim vb. için)
        scraper = ProductScraper(headless=True)
        product_data = scraper.scrape_single_product(url)
        
        # Bot başarısız olsa bile manuel fiyat varsa devam et
        if not product_data:
             if manual_price:
                 product_data = {'title': 'Manuel Ürün', 'image_url': '', 'platform': 'Manuel', 'category': 'Diğer', 'current_price': 0, 'original_price': 0}
             else:
                 return jsonify({'message': 'Ürün bilgileri çekilemedi.'}), 400
        
        # MANUEL FİYAT VARSA BOTU EZ
        if manual_price: 
            product_data['current_price'] = float(manual_price)
            print(f"✏️ Manuel Fiyat Kullanıldı: {manual_price}")

        if manual_old_price: 
            product_data['original_price'] = float(manual_old_price)
            
        # İndirim Hesabı (Otomatik)
        if product_data.get('original_price', 0) > product_data.get('current_price', 0):
            diff = product_data['original_price'] - product_data['current_price']
            product_data['discount_percent'] = int((diff / product_data['original_price']) * 100)
            if product_data['discount_percent'] > 20: product_data['real_deal_status'] = 'real'
        else:
            product_data['discount_percent'] = 0

        new_product = Product(
            title=product_data.get('title', 'Başlık Yok'),
            platform=product_data.get('platform', 'Diğer'),
            category=product_data.get('category', 'Genel'),
            current_price=product_data.get('current_price', 0),
            original_price=product_data.get('original_price', 0),
            discount_percent=product_data.get('discount_percent', 0),
            image_url=product_data.get('image_url', ''),
            product_url=url,
            real_deal_status=product_data.get('real_deal_status', 'normal')
        )
        
        db.session.add(new_product)
        db.session.commit()
        
        history = PriceHistory(product_id=new_product.id, price=new_product.current_price)
        db.session.add(history)
        db.session.commit()
        
        return jsonify({'message': '✅ Ürün başarıyla eklendi!', 'product': product_data}), 201

    except Exception as e:
        print(f"❌ Hata: {e}")
        return jsonify({'message': 'Sunucu hatası', 'error': str(e)}), 500

@app.route('/api/products/<int:id>', methods=['DELETE'])
def delete_product(id):
    product = Product.query.get_or_404(id)
    PriceHistory.query.filter_by(product_id=id).delete()
    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Silindi'})

def init_db():
    with app.app_context():
        db.create_all()

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
