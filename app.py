from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import csv
import io
import sys
from functools import wraps
from PIL import Image
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mcm_market_secret_key_2026_secure')

# PostgreSQL Database URL
DATABASE_URL = 'postgresql://mymarket_8q19_user:Hs2KnIFTlDPiz1vWfrPnLQ2dZUwhfN7B@dpg-d8i4gfmq1p3s73ebd8a0-a/mymarket_8q19'
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 300,
    'pool_pre_ping': True,
}

# Image upload
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def compress_image(image_path, max_size=(800, 800)):
    try:
        img = Image.open(image_path)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        img.save(image_path, optimize=True, quality=85)
    except:
        pass

# Database
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# ============ DATABASE MODELS ============

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='seller')
    is_super_admin = db.Column(db.Boolean, default=False)
    
    shop_name = db.Column(db.String(100))
    whatsapp_number = db.Column(db.String(20))
    email = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    suspended_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    products = db.relationship('Product', backref='seller', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        return self.role == 'admin'
    
    def is_seller(self):
        return self.role == 'seller'
    
    def suspend(self):
        self.is_active = False
        self.suspended_at = datetime.utcnow()
    
    def unsuspend(self):
        self.is_active = True
        self.suspended_at = None
    
    def get_id(self):
        return str(self.id)

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    whatsapp_number = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    image_filename = db.Column(db.String(500), nullable=True)
    category = db.Column(db.String(50), nullable=True)
    is_available = db.Column(db.Boolean, default=True, index=True)
    
    def get_image_url(self):
        if self.image_filename:
            return url_for('static', filename=f'uploads/{self.image_filename}')
        return None

class VisitLog(db.Model):
    __tablename__ = 'visit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50))
    heard_from = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_agent = db.Column(db.String(500))
    session_id = db.Column(db.String(100))
    referer = db.Column(db.String(200))

# ============ FORCE RECREATE TABLES ============

def init_db():
    """Initialize database with proper schema"""
    with app.app_context():
        try:
            # Drop all tables if they exist (for clean setup)
            db.drop_all()
            print("🗑️ Dropped existing tables")
            
            # Create all tables with proper schema
            db.create_all()
            print("✅ Database tables created successfully!")
            
            # Create super admin
            if not User.query.filter_by(username='Mpc', role='admin').first():
                admin = User(
                    username='Mpc',
                    role='admin',
                    is_super_admin=True,
                    is_active=True
                )
                admin.set_password('08800Mpc!')
                db.session.add(admin)
                db.session.commit()
                print("✅ Super admin created!")
            
            # Create test seller
            if not User.query.filter_by(username='testseller', role='seller').first():
                seller = User(
                    username='testseller',
                    role='seller',
                    shop_name='Test Shop',
                    whatsapp_number='123456789',
                    email='test@test.com',
                    is_active=True
                )
                seller.set_password('test123')
                db.session.add(seller)
                db.session.commit()
                print("✅ Test seller created!")
            
            # Create a sample product if none exist
            if not Product.query.first():
                seller = User.query.filter_by(role='seller').first()
                if seller:
                    product = Product(
                        name='Sample Product',
                        description='This is a sample product',
                        price=1000.00,
                        location='Test Location',
                        seller_id=seller.id,
                        whatsapp_number=seller.whatsapp_number,
                        category='Other',
                        is_available=True
                    )
                    db.session.add(product)
                    db.session.commit()
                    print("✅ Sample product created!")
            
        except Exception as e:
            print(f"⚠️ Database initialization error: {e}")
            db.session.rollback()

# Initialize database on startup
with app.app_context():
    try:
        # First check if tables exist
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        if not tables or 'users' not in tables:
            print("📦 Creating fresh database...")
            init_db()
        else:
            print("✅ Database already exists, checking schema...")
            # Check if products table has all columns
            if 'products' in tables:
                columns = [col['name'] for col in inspector.get_columns('products')]
                if 'name' not in columns:
                    print("⚠️ Products table missing columns, recreating...")
                    init_db()
                else:
                    print("✅ Schema is valid")
    except Exception as e:
        print(f"⚠️ Database check error: {e}")
        init_db()

# ============ LOGIN MANAGER ============

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except:
        return None

# ============ DECORATORS ============

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please login first', 'danger')
            return redirect(url_for('login'))
        if not current_user.is_admin():
            flash('Admin access required', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def super_admin_required(f):
    @wraps(f)
    @admin_required
    def decorated(*args, **kwargs):
        if not current_user.is_super_admin:
            flash('Super admin privileges required', 'danger')
            return redirect(url_for('admin_dashboard'))
        return f(*args, **kwargs)
    return decorated

def seller_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please login first', 'danger')
            return redirect(url_for('login'))
        if not current_user.is_seller():
            flash('Seller access required', 'danger')
            return redirect(url_for('index'))
        if not current_user.is_active:
            flash('Your account has been suspended', 'danger')
            return redirect(url_for('logout'))
        return f(*args, **kwargs)
    return decorated

# ============ ROUTES ============

@app.route('/')
def index():
    try:
        products = Product.query.filter(
            Product.is_available == True,
            Product.seller.has(is_active=True)
        ).order_by(Product.created_at.desc()).all()
        return render_template('index.html', products=products)
    except Exception as e:
        print(f"Index error: {e}")
        flash('Database error. Please try again.', 'danger')
        return render_template('index.html', products=[])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('seller_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                if not user.is_active:
                    flash('Account suspended. Contact admin.', 'danger')
                    return render_template('login.html')
                
                login_user(user)
                session['user_id'] = user.id
                session['user_role'] = user.role
                
                flash(f'Welcome {user.username}!', 'success')
                
                if user.is_admin():
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('seller_dashboard'))
        except Exception as e:
            print(f"Login error: {e}")
            flash('Database error. Please try again.', 'danger')
        
        flash('Invalid credentials', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

@app.route('/heard_from', methods=['POST'])
def heard_from():
    heard = request.form.get('heard_from')
    try:
        log = VisitLog(
            ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
            heard_from=heard,
            user_agent=request.headers.get('User-Agent', '')[:500],
            session_id=request.cookies.get('session', ''),
            referer=request.headers.get('Referer', '')
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"Heard from error: {e}")
        db.session.rollback()
    return redirect(url_for('index'))

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    try:
        products = Product.query.filter(
            Product.is_available == True,
            Product.seller.has(is_active=True)
        )
        if query:
            products = products.filter(
                Product.name.ilike(f'%{query}%') | 
                Product.description.ilike(f'%{query}%')
            )
        return render_template('index.html', products=products.all(), search_query=query)
    except Exception as e:
        print(f"Search error: {e}")
        return render_template('index.html', products=[], search_query=query)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        if not product.seller.is_active or not product.is_available:
            flash('Product not available', 'warning')
            return redirect(url_for('index'))
        return render_template('product_detail.html', product=product)
    except Exception as e:
        print(f"Product detail error: {e}")
        flash('Product not found', 'danger')
        return redirect(url_for('index'))

# ============ SELLER ROUTES ============

@app.route('/seller/dashboard')
@seller_required
def seller_dashboard():
    try:
        seller = current_user
        products = Product.query.filter_by(seller_id=seller.id).order_by(Product.created_at.desc()).all()
        return render_template('seller_dashboard.html', seller=seller, products=products)
    except Exception as e:
        print(f"Seller dashboard error: {e}")
        flash('Error loading dashboard', 'danger')
        return redirect(url_for('index'))

@app.route('/seller/product/add', methods=['GET', 'POST'])
@seller_required
def seller_add_product():
    seller = current_user
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            price = request.form.get('price')
            location = request.form.get('location')
            
            if not name or not price or not location:
                flash('Name, Price, and Location are required', 'danger')
                return render_template('add_product.html', seller=seller)
            
            price = float(price)
            
            product = Product(
                name=name,
                description=request.form.get('description'),
                price=price,
                location=location,
                seller_id=seller.id,
                whatsapp_number=seller.whatsapp_number,
                category=request.form.get('category')
            )
            
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    compress_image(filepath)
                    product.image_filename = filename
            
            db.session.add(product)
            db.session.commit()
            flash('Product uploaded successfully!', 'success')
            return redirect(url_for('seller_dashboard'))
        except Exception as e:
            print(f"Add product error: {e}")
            db.session.rollback()
            flash('Error adding product', 'danger')
    
    return render_template('add_product.html', seller=seller)

@app.route('/seller/product/<int:product_id>/delete')
@seller_required
def seller_delete_product(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        if product.seller_id != current_user.id:
            flash('Unauthorized action', 'danger')
            return redirect(url_for('seller_dashboard'))
        
        if product.image_filename:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], product.image_filename))
            except:
                pass
        
        db.session.delete(product)
        db.session.commit()
        flash('Product deleted successfully', 'success')
    except Exception as e:
        print(f"Delete product error: {e}")
        db.session.rollback()
        flash('Error deleting product', 'danger')
    return redirect(url_for('seller_dashboard'))

@app.route('/seller/product/<int:product_id>/edit', methods=['GET', 'POST'])
@seller_required
def seller_edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != current_user.id:
        flash('Unauthorized action', 'danger')
        return redirect(url_for('seller_dashboard'))
    
    if request.method == 'POST':
        try:
            product.name = request.form.get('name')
            product.description = request.form.get('description')
            product.price = float(request.form.get('price'))
            product.location = request.form.get('location')
            product.category = request.form.get('category')
            product.is_available = request.form.get('is_available') == 'on'
            
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    if product.image_filename:
                        try:
                            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], product.image_filename))
                        except:
                            pass
                    
                    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    compress_image(filepath)
                    product.image_filename = filename
            
            db.session.commit()
            flash('Product updated successfully!', 'success')
            return redirect(url_for('seller_dashboard'))
        except Exception as e:
            print(f"Edit product error: {e}")
            db.session.rollback()
            flash('Error updating product', 'danger')
    
    return render_template('edit_product.html', product=product, seller=current_user)

# ============ ADMIN ROUTES ============

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    try:
        sellers = User.query.filter_by(role='seller').order_by(User.created_at.desc()).all()
        admins = User.query.filter_by(role='admin').all()
        products = Product.query.order_by(Product.created_at.desc()).all()
        recent_logs = VisitLog.query.order_by(VisitLog.timestamp.desc()).limit(10).all()
        
        stats = {
            'total_sellers': User.query.filter_by(role='seller').count(),
            'active_sellers': User.query.filter_by(role='seller', is_active=True).count(),
            'total_products': Product.query.count(),
            'total_visits': VisitLog.query.count(),
            'today_visits': VisitLog.query.filter(
                VisitLog.timestamp >= datetime.utcnow().date()
            ).count()
        }
        
        return render_template('admin_dashboard.html', 
                             sellers=sellers, admins=admins, products=products,
                             recent_logs=recent_logs, **stats)
    except Exception as e:
        print(f"Admin dashboard error: {e}")
        flash('Error loading dashboard', 'danger')
        return render_template('admin_dashboard.html', sellers=[], admins=[], products=[], recent_logs=[])

@app.route('/admin/seller/create', methods=['GET', 'POST'])
@admin_required
def create_seller():
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            password = request.form.get('password')
            shop_name = request.form.get('shop_name')
            whatsapp = request.form.get('whatsapp')
            
            if not all([username, password, shop_name, whatsapp]):
                flash('All fields are required', 'danger')
                return render_template('create_seller.html')
            
            if User.query.filter_by(username=username).first():
                flash('Username already exists', 'danger')
                return render_template('create_seller.html')
            
            seller = User(
                username=username,
                role='seller',
                shop_name=shop_name,
                whatsapp_number=whatsapp,
                email=request.form.get('email'),
                is_active=True
            )
            seller.set_password(password)
            db.session.add(seller)
            db.session.commit()
            flash(f'Seller "{shop_name}" created successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            print(f"Create seller error: {e}")
            db.session.rollback()
            flash('Error creating seller', 'danger')
    
    return render_template('create_seller.html')

@app.route('/admin/seller/<int:seller_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_seller(seller_id):
    seller = User.query.get_or_404(seller_id)
    if seller.role != 'seller':
        flash('User is not a seller', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        try:
            seller.shop_name = request.form.get('shop_name')
            seller.whatsapp_number = request.form.get('whatsapp')
            seller.email = request.form.get('email')
            if request.form.get('password'):
                seller.set_password(request.form.get('password'))
            db.session.commit()
            flash('Seller updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            print(f"Edit seller error: {e}")
            db.session.rollback()
            flash('Error updating seller', 'danger')
    
    return render_template('edit_seller.html', seller=seller)

@app.route('/admin/seller/<int:seller_id>/toggle')
@admin_required
def toggle_seller(seller_id):
    try:
        seller = User.query.get_or_404(seller_id)
        if seller.role != 'seller':
            flash('User is not a seller', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        if seller.is_active:
            seller.suspend()
            flash(f'Seller "{seller.shop_name}" suspended', 'warning')
        else:
            seller.unsuspend()
            flash(f'Seller "{seller.shop_name}" unsuspended', 'success')
        db.session.commit()
    except Exception as e:
        print(f"Toggle seller error: {e}")
        db.session.rollback()
        flash('Error toggling seller', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/seller/<int:seller_id>/delete')
@admin_required
def delete_seller(seller_id):
    try:
        seller = User.query.get_or_404(seller_id)
        if seller.role != 'seller':
            flash('User is not a seller', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        for product in seller.products:
            if product.image_filename:
                try:
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], product.image_filename))
                except:
                    pass
        
        db.session.delete(seller)
        db.session.commit()
        flash('Seller deleted successfully', 'danger')
    except Exception as e:
        print(f"Delete seller error: {e}")
        db.session.rollback()
        flash('Error deleting seller', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/admin/create', methods=['GET', 'POST'])
@super_admin_required
def create_admin():
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            password = request.form.get('password')
            is_super = request.form.get('is_super') == 'on'
            
            if User.query.filter_by(username=username).first():
                flash('Username already exists', 'danger')
                return render_template('create_admin.html')
            
            admin = User(
                username=username,
                role='admin',
                is_super_admin=is_super,
                is_active=True
            )
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
            flash(f'Admin "{username}" created successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            print(f"Create admin error: {e}")
            db.session.rollback()
            flash('Error creating admin', 'danger')
    
    return render_template('create_admin.html')

@app.route('/admin/admin/<int:admin_id>/edit', methods=['GET', 'POST'])
@super_admin_required
def edit_admin(admin_id):
    admin = User.query.get_or_404(admin_id)
    if admin.role != 'admin':
        flash('User is not an admin', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    if admin.id == current_user.id:
        flash('Use profile settings to edit your own account', 'info')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        try:
            admin.username = request.form.get('username')
            if request.form.get('password'):
                admin.set_password(request.form.get('password'))
            admin.is_super_admin = request.form.get('is_super') == 'on'
            db.session.commit()
            flash('Admin updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            print(f"Edit admin error: {e}")
            db.session.rollback()
            flash('Error updating admin', 'danger')
    
    return render_template('edit_admin.html', admin=admin)

@app.route('/admin/admin/<int:admin_id>/delete')
@super_admin_required
def delete_admin(admin_id):
    try:
        admin = User.query.get_or_404(admin_id)
        if admin.role != 'admin':
            flash('User is not an admin', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        if admin.id == current_user.id:
            flash('Cannot delete your own account', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        db.session.delete(admin)
        db.session.commit()
        flash('Admin deleted successfully', 'danger')
    except Exception as e:
        print(f"Delete admin error: {e}")
        db.session.rollback()
        flash('Error deleting admin', 'danger')
    return redirect(url_for('admin_dashboard'))

# ============ LOGS MANAGEMENT ============

@app.route('/admin/logs')
@admin_required
def view_logs():
    try:
        date_from = request.args.get('from')
        date_to = request.args.get('to')
        heard_from = request.args.get('heard_from')
        
        query = VisitLog.query
        
        if date_from:
            try:
                date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
                query = query.filter(VisitLog.timestamp >= date_from_dt)
            except:
                pass
        
        if date_to:
            try:
                date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(VisitLog.timestamp <= date_to_dt)
            except:
                pass
        
        if heard_from and heard_from != 'all':
            query = query.filter(VisitLog.heard_from == heard_from)
        
        logs = query.order_by(VisitLog.timestamp.desc()).all()
        
        stats = {
            'total': VisitLog.query.count(),
            'internet': VisitLog.query.filter_by(heard_from='Internet').count(),
            'friend': VisitLog.query.filter_by(heard_from='Friend').count(),
            'research': VisitLog.query.filter_by(heard_from='Self Research').count()
        }
        
        return render_template('logs.html', logs=logs, stats=stats, 
                             date_from=date_from, date_to=date_to, heard_from=heard_from)
    except Exception as e:
        print(f"View logs error: {e}")
        flash('Error loading logs', 'danger')
        return render_template('logs.html', logs=[], stats={})

@app.route('/admin/logs/download')
@admin_required
def download_logs():
    try:
        date_from = request.args.get('from')
        date_to = request.args.get('to')
        
        query = VisitLog.query
        if date_from:
            try:
                query = query.filter(VisitLog.timestamp >= datetime.strptime(date_from, '%Y-%m-%d'))
            except:
                pass
        if date_to:
            try:
                query = query.filter(VisitLog.timestamp <= datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
            except:
                pass
        
        logs = query.all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'IP Address', 'Heard From', 'Timestamp', 'User Agent'])
        for log in logs:
            writer.writerow([log.id, log.ip_address, log.heard_from, log.timestamp, log.user_agent])
        
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    except Exception as e:
        print(f"Download logs error: {e}")
        flash('Error downloading logs', 'danger')
        return redirect(url_for('view_logs'))

@app.route('/admin/logs/delete', methods=['POST'])
@admin_required
def delete_logs():
    try:
        count = VisitLog.query.count()
        VisitLog.query.delete()
        db.session.commit()
        flash(f'Deleted {count} log records', 'success')
    except Exception as e:
        print(f"Delete logs error: {e}")
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('view_logs'))

# ============ API ENDPOINTS ============

@app.route('/api/products')
def api_products():
    try:
        products = Product.query.filter(
            Product.is_available == True,
            Product.seller.has(is_active=True)
        ).all()
        
        return jsonify([{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'price': p.price,
            'location': p.location,
            'shop_name': p.seller.shop_name,
            'whatsapp': p.whatsapp_number,
            'image': p.get_image_url()
        } for p in products])
    except Exception as e:
        print(f"API products error: {e}")
        return jsonify({'error': 'Error loading products'}), 500

@app.route('/api/stats')
@admin_required
def api_stats():
    try:
        return jsonify({
            'total_sellers': User.query.filter_by(role='seller').count(),
            'active_sellers': User.query.filter_by(role='seller', is_active=True).count(),
            'total_products': Product.query.count(),
            'total_visits': VisitLog.query.count(),
            'today_visits': VisitLog.query.filter(
                VisitLog.timestamp >= datetime.utcnow().date()
            ).count()
        })
    except Exception as e:
        print(f"API stats error: {e}")
        return jsonify({'error': 'Error loading stats'}), 500

# ============ ERROR HANDLERS ============

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    db.session.rollback()
    return render_template('500.html'), 500

# ============ MAIN ============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
