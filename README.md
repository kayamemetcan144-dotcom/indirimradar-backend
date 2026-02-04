# 🔥 İndirimRadar Backend API

Modern e-ticaret platformlarındaki gerçek indirimleri tespit eden REST API.

## 📋 Özellikler

- ✅ RESTful API architecture
- ✅ JWT Authentication & Authorization
- ✅ Admin panel güvenliği
- ✅ PostgreSQL database (Production)
- ✅ SQLite database (Development)
- ✅ Web scraping (Trendyol, Hepsiburada, N11)
- ✅ Otomatik fiyat takibi
- ✅ Fiyat alarm sistemi
- ✅ Pagination support
- ✅ CORS configuration
- ✅ Health check endpoint
- ✅ Production-ready with Gunicorn

## 🚀 Hızlı Başlangıç

### Gereksinimler

- Python 3.11+
- PostgreSQL (Production) veya SQLite (Development)

### Kurulum

1. **Repository'yi klonla:**
```bash
git clone https://github.com/kayamehmetcan144-alt/indirimradar-backend.git
cd indirimradar-backend
```

2. **Virtual environment oluştur:**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# veya
venv\Scripts\activate  # Windows
```

3. **Bağımlılıkları yükle:**
```bash
pip install -r requirements.txt
```

4. **Environment variables ayarla:**
```bash
cp .env.example .env
# .env dosyasını düzenle
```

5. **Database'i başlat:**
```bash
python
>>> from app import app, db
>>> with app.app_context():
>>>     db.create_all()
>>> exit()
```

6. **Uygulamayı çalıştır:**
```bash
python app.py
```

API şimdi `http://localhost:5000` adresinde çalışıyor.

## 📡 API Endpoints

### Authentication

#### Register
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response:**
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "is_premium": false,
    "is_admin": false
  }
}
```

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securepassword"
}
```

### Products

#### Get Products (Paginated)
```http
GET /api/products?category=Elektronik&platform=Trendyol&page=1&per_page=20
```

**Response:**
```json
{
  "products": [...],
  "total": 100,
  "pages": 5,
  "current_page": 1
}
```

#### Get Single Product
```http
GET /api/products/1
```

### Favorites (Authentication Required)

#### Get Favorites
```http
GET /api/favorites
Authorization: Bearer YOUR_JWT_TOKEN
```

#### Add to Favorites
```http
POST /api/favorites
Authorization: Bearer YOUR_JWT_TOKEN
Content-Type: application/json

{
  "product_id": 1
}
```

#### Remove from Favorites
```http
DELETE /api/favorites/1
Authorization: Bearer YOUR_JWT_TOKEN
```

### Price Alerts (Authentication Required)

#### Get Alerts
```http
GET /api/alerts
Authorization: Bearer YOUR_JWT_TOKEN
```

#### Create Alert
```http
POST /api/alerts
Authorization: Bearer YOUR_JWT_TOKEN
Content-Type: application/json

{
  "product_id": 1,
  "target_price": 5000
}
```

#### Delete Alert
```http
DELETE /api/alerts/1
Authorization: Bearer YOUR_JWT_TOKEN
```

### Stats

#### Get Statistics
```http
GET /api/stats
```

**Response:**
```json
{
  "total_products": 1245,
  "total_deals": 856,
  "avg_discount": 32.5
}
```

### Admin (Admin Privileges Required)

#### Create Product
```http
POST /api/admin/products
Authorization: Bearer ADMIN_JWT_TOKEN
Content-Type: application/json

{
  "title": "Product Name",
  "platform": "Trendyol",
  "category": "Elektronik",
  "current_price": 5000,
  "original_price": 8000,
  "discount_percent": 37,
  "image_url": "https://...",
  "product_url": "https://...",
  "real_deal_status": "real"
}
```

#### Update Product
```http
PUT /api/admin/products/1
Authorization: Bearer ADMIN_JWT_TOKEN
Content-Type: application/json

{
  "current_price": 4500
}
```

#### Delete Product
```http
DELETE /api/admin/products/1
Authorization: Bearer ADMIN_JWT_TOKEN
```

### Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2026-02-03T12:00:00"
}
```

## 🔒 Güvenlik

### JWT Token

Tüm korumalı endpoint'ler JWT token gerektirir:

```http
Authorization: Bearer YOUR_JWT_TOKEN
```

Token 30 gün geçerlidir.

### Admin Sistemi

Admin endpoint'leri ek `is_admin` kontrolü yapar:

```python
# Admin kullanıcı oluşturma (Database'de manuel)
user = User.query.filter_by(email='admin@indirimradar.com').first()
user.is_admin = True
db.session.commit()
```

### Güvenlik Özellikleri

- ✅ Password hashing (PBKDF2-SHA256)
- ✅ JWT token expiration
- ✅ Deleted user protection
- ✅ Input validation
- ✅ SQL injection protection
- ✅ CORS configuration
- ✅ Admin authorization

## 🗄️ Database Schema

### User
```python
id: Integer (Primary Key)
email: String (Unique)
password: String (Hashed)
is_premium: Boolean
is_admin: Boolean
created_at: DateTime
```

### Product
```python
id: Integer (Primary Key)
title: String
platform: String
category: String
current_price: Float
original_price: Float
discount_percent: Integer
image_url: String
product_url: String
real_deal_status: String (real/normal/fake)
created_at: DateTime
updated_at: DateTime
```

### PriceHistory
```python
id: Integer (Primary Key)
product_id: Integer (Foreign Key)
price: Float
recorded_at: DateTime
```

### Favorite
```python
id: Integer (Primary Key)
user_id: Integer (Foreign Key)
product_id: Integer (Foreign Key)
created_at: DateTime
```

### PriceAlert
```python
id: Integer (Primary Key)
user_id: Integer (Foreign Key)
product_id: Integer (Foreign Key)
target_price: Float
is_active: Boolean
created_at: DateTime
```

## 🕷️ Web Scraping

### Desteklenen Platformlar

- **Trendyol** (Selenium - Dynamic)
- **Hepsiburada** (Selenium - Dynamic)
- **N11** (Requests + BeautifulSoup - Static)

### Scraping Kullanımı

```python
from scraper import ProductScraper

scraper = ProductScraper(headless=True)

# Tüm platformlardan ürün topla
products = scraper.scrape_all_platforms()

# Tek platform
products = scraper.scrape_trendyol_category(
    'https://www.trendyol.com/elektronik-x-c103665',
    max_products=50
)
```

### Otomatik Scraping

```bash
python scheduler.py
```

Her 6 saatte bir otomatik çalışır ve:
- ✅ Yeni ürünleri ekler
- ✅ Fiyat geçmişini günceller
- ✅ Fiyat alarmlarını kontrol eder

## 🚀 Production Deployment

### Railway

1. **GitHub'a push et:**
```bash
git add .
git commit -m "Initial commit"
git push origin main
```

2. **Railway'e deploy et:**
- https://railway.app
- Deploy from GitHub
- Select repository
- Add PostgreSQL database

3. **Environment variables ekle:**
```env
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-key
FLASK_ENV=production
ALLOWED_ORIGINS=https://indirimradar.com,https://www.indirimradar.com
SCRAPING_ENABLED=true
LOG_LEVEL=INFO
```

4. **Deploy tamamlandı!**

### Heroku

```bash
heroku create indirimradar-api
heroku addons:create heroku-postgresql:mini
heroku config:set SECRET_KEY=your-secret-key
git push heroku main
```

## 🔧 Environment Variables

```env
# Flask
SECRET_KEY=your-super-secret-key
JWT_SECRET_KEY=your-jwt-secret-key
FLASK_ENV=production
FLASK_APP=app.py

# Database
DATABASE_URL=postgresql://user:pass@host:port/database

# CORS
ALLOWED_ORIGINS=https://indirimradar.com,https://www.indirimradar.com

# JWT
JWT_ACCESS_TOKEN_EXPIRES=2592000

# Scraping
SCRAPING_ENABLED=true
SCRAPING_INTERVAL_HOURS=6

# Logging
LOG_LEVEL=INFO
```

## 📊 Monitoring

### Health Check

```bash
curl https://your-api.railway.app/health
```

### Logs

```bash
# Railway
railway logs

# Heroku
heroku logs --tail
```

## 🧪 Testing

```bash
# Test health endpoint
curl http://localhost:5000/health

# Test register
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123"}'

# Test products
curl http://localhost:5000/api/products
```

## 📝 License

This project is proprietary and confidential.

## 👨‍💻 Author

İndirimRadar Development Team

## 🆘 Support

For issues and questions:
- GitHub Issues: https://github.com/kayamehmetcan144-alt/indirimradar-backend/issues
- Email: support@indirimradar.com

---

**🔥 İndirimRadar - Akıllı Alışveriş Asistanınız!**
