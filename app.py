from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_
import jwt
import os

app = Flask(__name__)

# ==================== CORS CONFIGURATION ====================
# Allow all origins for maximum compatibility
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# ==================== CONFIGURATION ====================
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'indirimradar-secret-key-2026')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', app.config['SECRET_KEY'])

# Database Configuration
database_url = os.getenv('DATABASE_URL', 'sqlite:///indirimradar.db')

# Fix Railway PostgreSQL URL
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

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
    real_deal_status = db.Column(db.String(20), default='real')  # real, normal, fake
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    price_history = db.relationship('PriceHistory', backref='product', lazy=True, cascade='all, delete-orphan')

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
        
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token.replace('Bearer ', '')
            
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
            
            if not current_user:
                return jsonify({'message': 'User not found'}), 401
                
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token'}), 401
        except Exception as e:
            return jsonify({'message': 'Authentication failed', 'error': str(e)}), 401
            
        return f(current_user, *args, **kwargs)
    
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'message': 'Admin access required'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token.replace('Bearer ', '')
            
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
            
            if not current_user or not current_user.is_admin:
                return jsonify({'message': 'Admin access required'}), 403
                
        except:
            return jsonify({'message': 'Authentication failed'}), 401
            
        return f(current_user, *args, **kwargs)
    
    return decorated

# ==================== HEALTH CHECK ====================

@app.route('/health', methods=['GET'])
def health():
    try:
        # Test database connection
        db.session.execute(db.text('SELECT 1'))
        db_status = 'connected'
    except Exception as e:
        db_status = f'error: {str(e)}'
    
    return jsonify({
        'status': 'healthy',
        'database': db_status,
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'message': '🔥 İndirimRadar API',
        'version': '1.0.0',
        'endpoints': {
            'auth': '/api/auth/login, /api/auth/register',
            'products': '/api/products',
            'admin': '/api/admin/products'
        }
    })

# ==================== AUTH ROUTES ====================

@app.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        
        # Validation
        if not data or 'email' not in data or 'password' not in data:
            return jsonify({'message': 'Email and password required'}), 400
        
        email = data['email'].strip().lower()
        password = data['password']
        
        # Email format check
        if '@' not in email or '.' not in email:
            return jsonify({'message': 'Invalid email format'}), 400
        
        # Password length check
        if len(password) < 6:
            return jsonify({'message': 'Password must be at least 6 characters'}), 400
        
        # Check if user exists
        if User.query.filter_by(email=email).first():
            return jsonify({'message': 'Email already registered'}), 409
        
        # Create user
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(email=email, password=hashed_password)
        
        db.session.add(new_user)
        db.session.commit()
        
        # Generate token
        token = jwt.encode({
            'user_id': new_user.id,
            'exp': datetime.utcnow() + timedelta(days=30)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        
        return jsonify({
            'message': 'Registration successful',
            'token': token,
            'user': {
                'id': new_user.id,
                'email': new_user.email,
                'is_premium': new_user.is_premium,
                'is_admin': new_user.is_admin
            }
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Registration failed', 'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        if not data or 'email' not in data or 'password' not in data:
            return jsonify({'message': 'Email and password required'}), 400
        
        email = data['email'].strip().lower()
        user = User.query.filter_by(email=email).first()
        
        if not user or not check_password_hash(user.password, data['password']):
            return jsonify({'message': 'Invalid credentials'}), 401
        
        token = jwt.encode({
            'user_id': user.id,
            'exp': datetime.utcnow() + timedelta(days=30)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        
        return jsonify({
            'token': token,
            'user': {
                'id': user.id,
                'email': user.email,
                'is_premium': user.is_premium,
                'is_admin': user.is_admin
            }
        })
    
    except Exception as e:
        return jsonify({'message': 'Login failed', 'error': str(e)}), 500

# ==================== PRODUCT ROUTES ====================

@app.route('/api/products', methods=['GET'])
def get_products():
    try:
        # Query parameters
        category = request.args.get('category', '')
        platform = request.args.get('platform', '')
        search = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 100))
        
        query = Product.query
        
        # Category filter
        if category and category not in ['all', 'Tümü', '']:
            query = query.filter(Product.category.ilike(f'%{category}%'))
        
        # Platform filter
        if platform and platform != '':
            query = query.filter_by(platform=platform)
        
        # Search filter
        if search:
            query = query.filter(
                or_(
                    Product.title.ilike(f'%{search}%'),
                    Product.platform.ilike(f'%{search}%'),
                    Product.category.ilike(f'%{search}%')
                )
            )
        
        # Order by discount and date
        query = query.order_by(
            Product.discount_percent.desc(), 
            Product.created_at.desc()
        )
        
        # Pagination
        products = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'products': [{
                'id': p.id,
                'title': p.title,
                'platform': p.platform,
                'category': p.category,
                'current_price': float(p.current_price),
                'original_price': float(p.original_price),
                'discount_percent': p.discount_percent,
                'image_url': p.image_url,
                'image': p.image_url,  # Compatibility
                'product_url': p.product_url,
                'url': p.product_url,  # Compatibility
                'real_deal_status': p.real_deal_status,
                'created_at': p.created_at.isoformat() if p.created_at else None,
                'updated_at': p.updated_at.isoformat() if p.updated_at else None
            } for p in products.items],
            'total': products.total,
            'pages': products.pages,
            'current_page': products.page,
            'per_page': per_page
        })
    
    except Exception as e:
        return jsonify({'message': 'Error fetching products', 'error': str(e)}), 500

@app.route('/api/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        
        return jsonify({
            'id': product.id,
            'title': product.title,
            'platform': product.platform,
            'category': product.category,
            'current_price': float(product.current_price),
            'original_price': float(product.original_price),
            'discount_percent': product.discount_percent,
            'image_url': product.image_url,
            'product_url': product.product_url,
            'real_deal_status': product.real_deal_status,
            'created_at': product.created_at.isoformat(),
            'updated_at': product.updated_at.isoformat()
        })
    
    except Exception as e:
        return jsonify({'message': 'Product not found', 'error': str(e)}), 404

# ==================== ADMIN ROUTES ====================

@app.route('/api/admin/products', methods=['POST'])
def create_product():
    """Create new product - No authentication required for development"""
    try:
        data = request.get_json()
        
        # Validation
        required_fields = ['title', 'platform', 'category', 'current_price', 'original_price', 'product_url', 'image_url']
        for field in required_fields:
            if field not in data:
                return jsonify({'message': f'Missing field: {field}'}), 400
        
        # Calculate discount
        discount = round(
            ((float(data['original_price']) - float(data['current_price'])) / float(data['original_price'])) * 100
        )
        
        # Create product
        product = Product(
            title=data['title'],
            platform=data['platform'],
            category=data['category'],
            current_price=float(data['current_price']),
            original_price=float(data['original_price']),
            discount_percent=discount,
            image_url=data['image_url'],
            product_url=data['product_url'],
            real_deal_status=data.get('real_deal_status', 'real')
        )
        
        db.session.add(product)
        db.session.commit()
        
        # Add price history
        history = PriceHistory(
            product_id=product.id,
            price=product.current_price
        )
        db.session.add(history)
        db.session.commit()
        
        return jsonify({
            'message': 'Product created successfully',
            'product': {
                'id': product.id,
                'title': product.title,
                'platform': product.platform,
                'current_price': product.current_price,
                'discount_percent': product.discount_percent
            }
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Error creating product', 'error': str(e)}), 500

@app.route('/api/admin/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    """Update product - No authentication required for development"""
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json()
        
        # Update fields
        if 'title' in data:
            product.title = data['title']
        if 'platform' in data:
            product.platform = data['platform']
        if 'category' in data:
            product.category = data['category']
        if 'image_url' in data:
            product.image_url = data['image_url']
        if 'product_url' in data:
            product.product_url = data['product_url']
        if 'real_deal_status' in data:
            product.real_deal_status = data['real_deal_status']
        
        # Update prices and recalculate discount
        if 'current_price' in data or 'original_price' in data:
            current = float(data.get('current_price', product.current_price))
            original = float(data.get('original_price', product.original_price))
            
            product.current_price = current
            product.original_price = original
            product.discount_percent = round(((original - current) / original) * 100)
            
            # Add price history if price changed
            if current != product.current_price:
                history = PriceHistory(product_id=product.id, price=current)
                db.session.add(history)
        
        product.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': 'Product updated successfully',
            'product': {
                'id': product.id,
                'title': product.title,
                'current_price': product.current_price,
                'discount_percent': product.discount_percent
            }
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Error updating product', 'error': str(e)}), 500

@app.route('/api/admin/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    """Delete product - No authentication required for development"""
    try:
        product = Product.query.get_or_404(product_id)
        
        # Delete related records
        PriceHistory.query.filter_by(product_id=product_id).delete()
        Favorite.query.filter_by(product_id=product_id).delete()
        PriceAlert.query.filter_by(product_id=product_id).delete()
        
        db.session.delete(product)
        db.session.commit()
        
        return jsonify({
            'message': 'Product deleted successfully',
            'id': product_id
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Error deleting product', 'error': str(e)}), 500

# ==================== STATS ROUTE ====================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        total_products = Product.query.count()
        total_users = User.query.count()
        
        if total_products > 0:
            avg_discount = db.session.query(
                db.func.avg(Product.discount_percent)
            ).scalar() or 0
            
            best_deal = db.session.query(
                db.func.max(Product.discount_percent)
            ).scalar() or 0
        else:
            avg_discount = 0
            best_deal = 0
        
        return jsonify({
            'total_products': total_products,
            'total_users': total_users,
            'avg_discount': round(avg_discount, 2),
            'best_deal': best_deal
        })
    
    except Exception as e:
        return jsonify({'message': 'Error fetching stats', 'error': str(e)}), 500

# ==================== INITIALIZE DATABASE ====================

def init_db():
    """Initialize database with tables and sample data"""
    with app.app_context():
        try:
            print("🔄 Creating database tables...")
            db.create_all()
            print("✅ Tables created!")
            
            # Add sample data if database is empty
            if Product.query.count() == 0:
                print("📦 Adding sample data...")
                sample_products = [
                    {
                        'title': 'iPhone 15 Pro Max 256GB',
                        'platform': 'Trendyol',
                        'category': 'Elektronik',
                        'current_price': 67499.0,
                        'original_price': 89999.0,
                        'discount_percent': 25,
                        'image_url': 'https://images.unsplash.com/photo-1696446702001-80b18e0879f9?w=500&q=80',
                        'product_url': 'https://www.trendyol.com',
                        'real_deal_status': 'real'
                    },
                    {
                        'title': 'Samsung 65" QLED 4K Smart TV',
                        'platform': 'Hepsiburada',
                        'category': 'Elektronik',
                        'current_price': 32999.0,
                        'original_price': 45999.0,
                        'discount_percent': 28,
                        'image_url': 'https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=500&q=80',
                        'product_url': 'https://www.hepsiburada.com',
                        'real_deal_status': 'real'
                    },
                    {
                        'title': 'Nike Air Max 270 Erkek Spor Ayakkabı',
                        'platform': 'N11',
                        'category': 'Moda',
                        'current_price': 2999.0,
                        'original_price': 4999.0,
                        'discount_percent': 40,
                        'image_url': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=500&q=80',
                        'product_url': 'https://www.n11.com',
                        'real_deal_status': 'real'
                    }
                ]
                
                for data in sample_products:
                    product = Product(**data)
                    db.session.add(product)
                    db.session.commit()
                    
                    # Add price history
                    history = PriceHistory(product_id=product.id, price=data['current_price'])
                    db.session.add(history)
                
                db.session.commit()
                print("✅ Sample data added!")
            else:
                print("ℹ️ Sample data already exists")
            
            # Add admin user if not exists
            admin = User.query.filter_by(email='admin@indirimradar.com').first()
            if not admin:
                admin = User(
                    email='admin@indirimradar.com',
                    password=generate_password_hash('Admin123!', method='pbkdf2:sha256'),
                    is_admin=True
                )
                db.session.add(admin)
                db.session.commit()
                print('✅ Admin user created!')
            else:
                print('ℹ️ Admin user already exists')
        
        except Exception as e:
            print(f"⚠️ Database initialization error: {e}")
            db.session.rollback()

# ==================== INITIALIZE ON STARTUP ====================

try:
    init_db()
    print("🔄 Database initialization completed")
except Exception as e:
    print(f"⚠️ Database initialization error: {e}")

# ==================== RUN ====================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    is_production = os.getenv('FLASK_ENV') == 'production'
    
    app.run(
        debug=not is_production,
        host='0.0.0.0',
        port=port
    )
