from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text
import jwt
import os

app = Flask(__name__)

# CORS Yapılandırması
allowed_origins = os.getenv('ALLOWED_ORIGINS', '*').split(',')
CORS(app, origins=allowed_origins)

# Gizli Anahtar Ayarları
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', app.config['SECRET_KEY'])

# Veritabanı Bağlantısı - Railway PostgreSQL Desteği
database_url = os.getenv('DATABASE_URL', 'sqlite:///indirimradar.db')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///indirimradar.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True, 'pool_recycle': 300}

db = SQLAlchemy(app)

# ==================== MODELLER ====================

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

# ==================== OTOMATİK KURULUM VE ADMIN OLUŞTURMA ====================

with app.app_context():
    db.create_all()
    
    # 1. Örnek Ürün Kontrolü
    if Product.query.count() == 0:
        sample_products = [
            {'title': 'iPhone 15 Pro Max', 'platform': 'Trendyol', 'category': 'Elektronik', 
             'current_price': 67499, 'original_price': 89999, 'discount_percent': 25, 
             'image_url': 'https://images.unsplash.com/photo-1696446702001-80b18e0879f9', 
             'product_url': 'https://www.trendyol.com'}
        ]
        for data in sample_products:
            p = Product(**data)
            db.session.add(p)
        db.session.commit()
        print("✅ Örnek veriler eklendi.")

    # 2. ADMIN KULLANICISI OLUŞTURMA (ÖNEMLİ KISIM)
    admin_email = "admin@indirimradar.com"
    admin_user = User.query.filter_by(email=admin_email).first()
    
    if not admin_user:
        # Şifre: admin123
        hashed_pw = generate_password_hash("admin123", method='pbkdf2:sha256')
        new_admin = User(
            email=admin_email,
            password=hashed_pw,
            is_premium=True,
            is_admin=True
        )
        db.session.add(new_admin)
        db.session.commit()
        print(f"😎 Admin oluşturuldu: {admin_email} / Şifre: admin123")
    else:
        print("👍 Admin kullanıcısı zaten mevcut.")

# ==================== ROTALAR ====================

@app.route('/health', methods=['GET'])
def health_check():
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({'status': 'healthy', 'database': 'connected'}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@app.route('/api/products', methods=['GET'])
def get_products():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    query = Product.query.order_by(Product.discount_percent.desc())
    products = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'products': [{
            'id': p.id, 'title': p.title, 'newPrice': p.current_price, 'discount': p.discount_percent, 'image': p.image_url
        } for p in products.items],
        'total': products.total
    })

# --- GİRİŞ VE KAYIT (Admin hesabına girmek için gerekli) ---

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data or 'email' not in data or 'password' not in data:
            return jsonify({'message': 'Email ve şifre gerekli'}), 400
        
        email = data['email'].strip().lower()
        user = User.query.filter_by(email=email).first()
        
        if not user or not check_password_hash(user.password, data['password']):
            return jsonify({'message': 'Geçersiz bilgiler'}), 401
        
        # Token oluştur
        token = jwt.encode({
            'user_id': user.id,
            'exp': datetime.utcnow() + timedelta(days=30)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        
        return jsonify({
            'token': token,
            'user': {
                'id': user.id,
                'email': user.email,
                'is_admin': user.is_admin,
                'is_premium': user.is_premium
            }
        })
    except Exception as e:
        return jsonify({'message': 'Giriş hatası', 'error': str(e)}), 500

@app.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password')

        if User.query.filter_by(email=email).first():
            return jsonify({'message': 'Kullanıcı zaten var'}), 400

        new_user = User(
            email=email,
            password=generate_password_hash(password, method='pbkdf2:sha256')
        )
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'message': 'Kayıt başarılı'}), 201
    except Exception as e:
        return jsonify({'message': 'Kayıt hatası', 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
