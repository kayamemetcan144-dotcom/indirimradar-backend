from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text
import jwt
import os

# Scraper'ı çağırıyoruz
from scraper import ProductScraper 

app = Flask(__name__)

# CORS Configuration
allowed_origins = os.getenv('ALLOWED_ORIGINS', '*').split(',')
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', app.config['SECRET_KEY'])

# Database Configuration
database_url = os.getenv('DATABASE_URL', 'sqlite:///indirimradar.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True, 'pool_recycle': 300}

db = SQLAlchemy(app)

# ==================== MODELS ====================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_premium = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    favorites = db.relationship('Favorite', backref='user', lazy=True, cascade='all, delete-orphan')
    alerts = db.relationship('PriceAlert', backref='user', lazy=True, cascade='all, delete-orphan')

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
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    price_history = db.relationship('PriceHistory', backref='product', lazy=True)

class PriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PriceAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    target_price = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== AUTH DECORATOR ====================

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token: return jsonify({'message': 'Token is missing'}), 401
        try:
            token = token.replace('Bearer ', '')
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
            if not current_user: return jsonify({'message': 'User no longer exists'}), 401
        except Exception as e: return jsonify({'message': 'Auth error', 'error': str(e)}), 401
        return f(current_user, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if not current_user.is_admin: return jsonify({'message': 'Admin required'}), 403
        return f(current_user, *args, **kwargs)
    return decorated

# ==================== AUTH ROUTES ====================

@app.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data or 'email' not in data or 'password' not in data:
            return jsonify({'message': 'Email and password required'}), 400
        
        email = data['email'].strip().lower()
        if User.query.filter_by(email=email).first():
            return jsonify({'message': 'User already exists'}), 400
        
        new_user = User(email=email, password=generate_password_hash(data['password'], method='pbkdf2:sha256'))
        db.session.add(new_user)
        db.session.commit()
        
        token = jwt.encode({'user_id': new_user.id, 'exp': datetime.utcnow() + timedelta(days=30)}, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({'token': token, 'user': {'id': new_user.id, 'email': new_user.email}}), 201
    except Exception as e: return jsonify({'message': 'Error', 'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data or 'email' not in data or 'password' not in data: return jsonify({'message': 'Missing data'}), 400
        
        user = User.query.filter_by(email=data['email'].strip().lower()).first()
        if not user or not check_password_hash(user.password, data['password']):
            return jsonify({'message': 'Invalid credentials'}), 401
        
        token = jwt.encode({'user_id': user.id, 'exp': datetime.utcnow() + timedelta(days=30)}, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({'token': token, 'user': {'id': user.id, 'email': user.email, 'is_admin': user.is_admin}})
    except Exception as e: return jsonify({'message': 'Error', 'error': str(e)}), 500

# ==================== PRODUCT ROUTES (GÜNCELLENDİ) ====================

@app.route('/api/products', methods=['GET'])
def get_products():
    page = int(request.args.get('page', 1))
    # En yeni eklenenler en üstte olsun
    products = Product.query.order_by(Product.id.desc()).paginate(page=page, per_page=20, error_out=False)
    
    return jsonify({
        'products': [{
            'id': p.id,
            'title': p.title,
            'platform': p.platform,
            'current_price': p.current_price,
            'original_price': p.original_price,
            'discount_percent': p.discount_percent,
            'image_url': p.image_url,
            'url': p.product_url,
            'real_deal_status': p.real_deal_status
        } for p in products.items],
        'total': products.total,
        'pages': products.pages,
        'current_page': products.page
    })

# --- YENİ EKLENEN ÖZELLİK: MANUEL FİYAT DESTEĞİ ---
@app.route('/api/products', methods=['POST'])
def add_product_via_link():
    data = request.get_json()
    url = data.get('url')
    
    # Ön yüzden gelen manuel fiyatlar (varsa)
    manual_price = data.get('manual_price') # Satış Fiyatı (İndirimli)
    manual_old_price = data.get('manual_old_price') # Normal Fiyat (Üstü Çizili)
    
    if not url:
        return jsonify({'message': 'URL gerekli'}), 400

    existing = Product.query.filter_by(product_url=url).first()
    if existing:
        return jsonify({'message': 'Bu ürün zaten takip ediliyor', 'id': existing.id}), 200

    try:
        print(f"🕵️‍♂️ Scraping başlatılıyor: {url}")
        
        # 1. Önce Bot Bilgileri Çeksin (Resim, Başlık vb. için)
        scraper = ProductScraper(headless=True)
        product_data = scraper.scrape_single_product(url)
        
        if not product_data:
            # Bot tamamen patlarsa ama manuel fiyat varsa, manuel veriyle devam etmeyi dene
             if manual_price:
                 product_data = {
                     'title': 'Manuel Eklenen Ürün',
                     'image_url': 'https://via.placeholder.com/300', # Yer tutucu resim
                     'platform': 'Manuel',
                     'category': 'Diğer'
                 }
             else:
                 return jsonify({'message': 'Ürün bilgileri çekilemedi.'}), 400
        
        # 2. MANUEL FİYAT KONTROLÜ (En Önemli Kısım)
        # Eğer kullanıcı elle fiyat girdiyse, botun bulduğu fiyatı ez!
        if manual_price:
            try:
                product_data['current_price'] = float(manual_price)
                print(f"✏️ Manuel Satış Fiyatı Kullanıldı: {product_data['current_price']}")
            except: pass
            
        if manual_old_price:
            try:
                product_data['original_price'] = float(manual_old_price)
                print(f"✏️ Manuel Eski Fiyat Kullanıldı: {product_data['original_price']}")
            except: pass
            
        # Eğer manuel giriş varsa İndirim Oranını tekrar hesapla
        if manual_price and manual_old_price:
            if product_data['original_price'] > product_data['current_price']:
                diff = product_data['original_price'] - product_data['current_price']
                product_data['discount_percent'] = int((diff / product_data['original_price']) * 100)
                if product_data['discount_percent'] > 20: 
                    product_data['real_deal_status'] = 'real'
                else:
                    product_data['real_deal_status'] = 'normal'
            else:
                product_data['discount_percent'] = 0

        # 3. Veritabanına kaydet
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
        
        # Fiyat geçmişine de ekle
        history = PriceHistory(product_id=new_product.id, price=new_product.current_price)
        db.session.add(history)
        db.session.commit()
        
        return jsonify({'message': '✅ Ürün başarıyla eklendi!', 'product': product_data}), 201

    except Exception as e:
        print(f"❌ Hata: {e}")
        return jsonify({'message': 'Sunucu hatası', 'error': str(e)}), 500

@app.route('/api/products/<int:id>', methods=['DELETE'])
@token_required
@admin_required
def delete_product(current_user, id):
    product = Product.query.get_or_404(id)
    PriceHistory.query.filter_by(product_id=id).delete()
    Favorite.query.filter_by(product_id=id).delete()
    PriceAlert.query.filter_by(product_id=id).delete()
    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Ürün silindi'})

# ==================== INITIALIZE ====================

def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email='admin@indirimradar.com').first():
            admin = User(
                email='admin@indirimradar.com',
                password=generate_password_hash('Admin123!', method='pbkdf2:sha256'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin oluşturuldu.")

init_db()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
