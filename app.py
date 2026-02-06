from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text
import jwt
import os

# --- YENİ EKLENEN: Scraper'ı çağırıyoruz ---
from scraper import ProductScraper 

app = Flask(__name__)

# CORS Configuration
allowed_origins = os.getenv('ALLOWED_ORIGINS', '*').split(',')
CORS(app, resources={r"/api/*": {"origins": "*"}}) # Tüm kapıları açtık (Garanti olsun)

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

# ==================== MODELS (Aynı Kalıyor) ====================

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

# 1. GET Products (Listeleme)
@app.route('/api/products', methods=['GET'])
def get_products():
    page = int(request.args.get('page', 1))
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

# 2. POST Products (YENİ - Link ile Ekleme - SCRAPING BURADA!)
@app.route('/api/products', methods=['POST'])
def add_product_via_link():
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({'message': 'URL gerekli'}), 400

    # 1. Önce bu ürün zaten var mı bakalım
    existing = Product.query.filter_by(product_url=url).first()
    if existing:
        return jsonify({'message': 'Bu ürün zaten takip ediliyor', 'id': existing.id}), 200

    # 2. Yoksa Scraper'ı çalıştır
    try:
        print(f"🕵️‍♂️ Scraping başlatılıyor: {url}")
        scraper = ProductScraper(headless=True)
        product_data = scraper.scrape_single_product(url)
        
        if not product_data:
            return jsonify({'message': 'Ürün bilgileri çekilemedi. Linki kontrol edin.'}), 400
        
        # 3. Veritabanına kaydet
        new_product = Product(
            title=product_data['title'],
            platform=product_data['platform'],
            category=product_data['category'],
            current_price=product_data['current_price'],
            original_price=product_data['original_price'],
            discount_percent=product_data['discount_percent'],
            image_url=product_data['image_url'],
            product_url=product_data['product_url'],
            real_deal_status='normal'
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

# 3. DELETE Product (Silme)
@app.route('/api/products/<int:id>', methods=['DELETE'])
def delete_product(id):
    # Basitlik için admin kontrolü kapalı, herkes silebilir (Demo modu)
    product = Product.query.get_or_404(id)
    
    # İlişkili kayıtları temizle
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
        # Admin User Ekle
        if not User.query.filter_by(email='admin@indirimradar.com').first():
            admin = User(
                email='admin@indirimradar.com',
                password=generate_password_hash('Admin123!', method='pbkdf2:sha256'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin oluşturuldu.")

# Başlangıçta çalıştır
init_db()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
