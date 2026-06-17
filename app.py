from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import json
import csv
import io
import sys
from functools import wraps

# Fix for Python 3.14 compatibility
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mcm_market_secret_key_2026_secure')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///mcm_market.db')
# Fix for PostgreSQL on Render
if app.config['SQLALCHEMY_DATABASE_URI'] and app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
    'pool_recycle': 300,
    'pool_pre_ping': True,
}

# Initialize database
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'
login_manager.login_message_category = 'info'

# ============ DATABASE MODELS ============

class Admin(UserMixin, db.Model):
    """Admin users model"""
    __tablename__ = 'admins'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    is_super_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<Admin {self.username}>'

class Seller(db.Model):
    """Seller accounts model"""
    __tablename__ = 'sellers'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    shop_name = db.Column(db.String(100), nullable=False)
    whatsapp_number = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    suspended_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    products = db.relationship('Product', backref='seller', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def suspend(self):
        self.is_active = False
        self.suspended_at = datetime.utcnow()
    
    def unsuspend(self):
        self.is_active = True
        self.suspended_at = None
    
    def __repr__(self):
        return f'<Seller {self.shop_name}>'

class Product(db.Model):
    """Products uploaded by sellers"""
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('sellers.id', ondelete='CASCADE'), nullable=False)
    whatsapp_number = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    image_url = db.Column(db.String(500), nullable=True)
    category = db.Column(db.String(50), nullable=True)
    is_available = db.Column(db.Boolean, default=True, index=True)
    
    def __repr__(self):
        return f'<Product {self.name}>'

class VisitLog(db.Model):
    """Visitor tracking logs"""
    __tablename__ = 'visit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50))
    heard_from = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_agent = db.Column(db.String(500))
    session_id = db.Column(db.String(100))
    referer = db.Column(db.String(200))
    
    def __repr__(self):
        return f'<VisitLog {self.id} - {self.heard_from}>'

# ============ CREATE TABLES ============

with app.app_context():
    try:
        db.create_all()
        print("Database tables created successfully!")
        
        # Create super admin if not exists
        if not Admin.query.filter_by(username='Mpc').first():
            super_admin = Admin(
                username='Mpc',
                is_super_admin=True
            )
            super_admin.set_password(os.environ.get('ADMIN_PASSWORD', '08800Mpc!'))
            db.session.add(super_admin)
            db.session.commit()
            print("Super admin created successfully!")
        else:
            print("Super admin already exists")
    except Exception as e:
        print(f"Database initialization error: {e}")

# ============ LOGIN MANAGER ============

@login_manager.user_loader
def load_user(user_id):
    try:
        return Admin.query.get(int(user_id))
    except:
        return None

# ============ DECORATORS ============

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please login as admin first', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    @wraps(f)
    @admin_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_super_admin:
            flash('Super admin privileges required', 'danger')
            return redirect(url_for('admin_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def seller_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'seller_id' not in session:
            flash('Please login as seller first', 'danger')
            return redirect(url_for('seller_login'))
        seller = Seller.query.get(session['seller_id'])
        if not seller or not seller.is_active:
            session.clear()
            flash('Your account has been suspended', 'danger')
            return redirect(url_for('seller_login'))
        return f(*args, **kwargs)
    return decorated_function

# ============ PUBLIC ROUTES ============

@app.route('/')
def index():
    products = Product.query.filter(
        Product.is_available == True,
        Product.seller.has(is_active=True)
    ).order_by(Product.created_at.desc()).all()
    return render_template('index.html', products=products)

@app.route('/heard_from', methods=['POST'])
def heard_from():
    heard = request.form.get('heard_from')
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent', '')
    session_id = request.cookies.get('session', '')
    referer = request.headers.get('Referer', '')
    
    log = VisitLog(
        ip_address=ip,
        heard_from=heard,
        user_agent=user_agent[:500],
        session_id=session_id,
        referer=referer
    )
    db.session.add(log)
    db.session.commit()
    
    return redirect(url_for('index'))

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if query:
        products = Product.query.filter(
            (Product.name.contains(query) | Product.description.contains(query)),
            Product.is_available == True,
            Product.seller.has(is_active=True)
        ).all()
    else:
        products = Product.query.filter(
            Product.is_available == True,
            Product.seller.has(is_active=True)
        ).all()
    return render_template('index.html', products=products, search_query=query)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.seller.is_active or not product.is_available:
        flash('This product is not available', 'warning')
        return redirect(url_for('index'))
    return render_template('product_detail.html', product=product)

# ============ SELLER ROUTES ============

@app.route('/seller/login', methods=['GET', 'POST'])
def seller_login():
    if 'seller_id' in session:
        return redirect(url_for('seller_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        seller = Seller.query.filter_by(username=username).first()
        if seller and seller.check_password(password):
            if not seller.is_active:
                flash('Your account has been suspended. Contact admin.', 'danger')
                return render_template('seller_login.html')
            
            session['seller_id'] = seller.id
            session['seller_name'] = seller.shop_name
            flash(f'Welcome back, {seller.shop_name}!', 'success')
            return redirect(url_for('seller_dashboard'))
        
        flash('Invalid credentials', 'danger')
    
    return render_template('seller_login.html')

@app.route('/seller/logout')
def seller_logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

@app.route('/seller/dashboard')
@seller_required
def seller_dashboard():
    seller = Seller.query.get(session['seller_id'])
    products = Product.query.filter_by(seller_id=seller.id).order_by(Product.created_at.desc()).all()
    return render_template('seller_dashboard.html', seller=seller, products=products)

@app.route('/seller/product/add', methods=['GET', 'POST'])
@seller_required
def seller_add_product():
    seller = Seller.query.get(session['seller_id'])
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        location = request.form.get('location')
        category = request.form.get('category')
        
        if not name or not price or not location:
            flash('Name, Price, and Location are required', 'danger')
            return render_template('add_product.html', seller=seller)
        
        try:
            price = float(price)
        except ValueError:
            flash('Invalid price format', 'danger')
            return render_template('add_product.html', seller=seller)
        
        product = Product(
            name=name,
            description=description,
            price=price,
            location=location,
            seller_id=seller.id,
            whatsapp_number=seller.whatsapp_number,
            category=category
        )
        
        db.session.add(product)
        db.session.commit()
        flash('Product uploaded successfully!', 'success')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('add_product.html', seller=seller)

@app.route('/seller/product/<int:product_id>/delete')
@seller_required
def seller_delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != session['seller_id']:
        flash('Unauthorized action', 'danger')
        return redirect(url_for('seller_dashboard'))
    
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/seller/product/<int:product_id>/edit', methods=['GET', 'POST'])
@seller_required
def seller_edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != session['seller_id']:
        flash('Unauthorized action', 'danger')
        return redirect(url_for('seller_dashboard'))
    
    seller = Seller.query.get(session['seller_id'])
    
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.description = request.form.get('description')
        product.price = float(request.form.get('price'))
        product.location = request.form.get('location')
        product.category = request.form.get('category')
        product.is_available = request.form.get('is_available') == 'on'
        
        db.session.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('edit_product.html', product=product, seller=seller)

# ============ ADMIN ROUTES ============

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            login_user(admin)
            flash('Welcome back, Admin!', 'success')
            return redirect(url_for('admin_dashboard'))
        
        flash('Invalid credentials', 'danger')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
@admin_required
def admin_logout():
    logout_user()
    flash('Logged out successfully', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    total_sellers = Seller.query.count()
    active_sellers = Seller.query.filter_by(is_active=True).count()
    total_products = Product.query.count()
    total_visits = VisitLog.query.count()
    today_visits = VisitLog.query.filter(
        VisitLog.timestamp >= datetime.utcnow().date()
    ).count()
    
    recent_logs = VisitLog.query.order_by(VisitLog.timestamp.desc()).limit(10).all()
    sellers = Seller.query.order_by(Seller.created_at.desc()).all()
    admins = Admin.query.all()
    products = Product.query.order_by(Product.created_at.desc()).all()
    
    return render_template('admin_dashboard.html',
                         sellers=sellers,
                         admins=admins,
                         products=products,
                         total_sellers=total_sellers,
                         active_sellers=active_sellers,
                         total_products=total_products,
                         total_visits=total_visits,
                         today_visits=today_visits,
                         recent_logs=recent_logs)

# ============ SELLER MANAGEMENT (ADMIN) ============

@app.route('/admin/seller/create', methods=['GET', 'POST'])
@admin_required
def create_seller():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        shop_name = request.form.get('shop_name')
        whatsapp = request.form.get('whatsapp')
        email = request.form.get('email')
        
        if not username or not password or not shop_name or not whatsapp:
            flash('All fields are required', 'danger')
            return render_template('create_seller.html')
        
        if Seller.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return render_template('create_seller.html')
        
        seller = Seller(
            username=username,
            shop_name=shop_name,
            whatsapp_number=whatsapp,
            email=email
        )
        seller.set_password(password)
        
        db.session.add(seller)
        db.session.commit()
        
        flash(f'Seller account "{shop_name}" created successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('create_seller.html')

@app.route('/admin/seller/<int:seller_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_seller(seller_id):
    seller = Seller.query.get_or_404(seller_id)
    
    if request.method == 'POST':
        seller.shop_name = request.form.get('shop_name')
        seller.whatsapp_number = request.form.get('whatsapp')
        seller.email = request.form.get('email')
        
        if request.form.get('password'):
            seller.set_password(request.form.get('password'))
        
        db.session.commit()
        flash('Seller updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('edit_seller.html', seller=seller)

@app.route('/admin/seller/<int:seller_id>/toggle')
@admin_required
def toggle_seller(seller_id):
    seller = Seller.query.get_or_404(seller_id)
    
    if seller.is_active:
        seller.suspend()
        flash(f'Seller "{seller.shop_name}" has been suspended', 'warning')
    else:
        seller.unsuspend()
        flash(f'Seller "{seller.shop_name}" has been unsuspended', 'success')
    
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/seller/<int:seller_id>/delete')
@admin_required
def delete_seller(seller_id):
    seller = Seller.query.get_or_404(seller_id)
    shop_name = seller.shop_name
    
    db.session.delete(seller)
    db.session.commit()
    
    flash(f'Seller "{shop_name}" and all products deleted', 'danger')
    return redirect(url_for('admin_dashboard'))

# ============ ADMIN MANAGEMENT ============

@app.route('/admin/admin/create', methods=['GET', 'POST'])
@super_admin_required
def create_admin():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        is_super = request.form.get('is_super') == 'on'
        
        if Admin.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return render_template('create_admin.html')
        
        admin = Admin(
            username=username,
            is_super_admin=is_super
        )
        admin.set_password(password)
        
        db.session.add(admin)
        db.session.commit()
        
        flash(f'Admin "{username}" created successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('create_admin.html')

@app.route('/admin/admin/<int:admin_id>/edit', methods=['GET', 'POST'])
@super_admin_required
def edit_admin(admin_id):
    admin = Admin.query.get_or_404(admin_id)
    
    if admin.id == current_user.id:
        flash('Use profile settings to edit your own account', 'info')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        admin.username = request.form.get('username')
        if request.form.get('password'):
            admin.set_password(request.form.get('password'))
        admin.is_super_admin = request.form.get('is_super') == 'on'
        
        db.session.commit()
        flash('Admin updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('edit_admin.html', admin=admin)

@app.route('/admin/admin/<int:admin_id>/delete')
@super_admin_required
def delete_admin(admin_id):
    admin = Admin.query.get_or_404(admin_id)
    
    if admin.id == current_user.id:
        flash('Cannot delete your own account', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    username = admin.username
    db.session.delete(admin)
    db.session.commit()
    
    flash(f'Admin "{username}" deleted', 'danger')
    return redirect(url_for('admin_dashboard'))

# ============ LOGS MANAGEMENT ============

@app.route('/admin/logs')
@admin_required
def view_logs():
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    heard_from = request.args.get('heard_from')
    
    query = VisitLog.query
    
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(VisitLog.timestamp >= date_from_dt)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(VisitLog.timestamp <= date_to_dt)
        except ValueError:
            pass
    
    if heard_from and heard_from != 'all':
        query = query.filter(VisitLog.heard_from == heard_from)
    
    logs = query.order_by(VisitLog.timestamp.desc()).all()
    
    total_logs = VisitLog.query.count()
    internet_count = VisitLog.query.filter_by(heard_from='Internet').count()
    friend_count = VisitLog.query.filter_by(heard_from='Friend').count()
    research_count = VisitLog.query.filter_by(heard_from='Self Research').count()
    
    return render_template('logs.html', 
                         logs=logs,
                         total_logs=total_logs,
                         internet_count=internet_count,
                         friend_count=friend_count,
                         research_count=research_count,
                         date_from=date_from,
                         date_to=date_to,
                         heard_from=heard_from)

@app.route('/admin/logs/download')
@admin_required
def download_logs():
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    heard_from = request.args.get('heard_from')
    
    query = VisitLog.query
    
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(VisitLog.timestamp >= date_from_dt)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(VisitLog.timestamp <= date_to_dt)
        except ValueError:
            pass
    
    if heard_from and heard_from != 'all':
        query = query.filter(VisitLog.heard_from == heard_from)
    
    logs = query.order_by(VisitLog.timestamp.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'IP Address', 'Heard From', 'Timestamp', 'User Agent', 'Session ID', 'Referer'])
    
    for log in logs:
        writer.writerow([
            log.id,
            log.ip_address,
            log.heard_from,
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.user_agent,
            log.session_id,
            log.referer
        ])
    
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'visit_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

@app.route('/admin/logs/delete', methods=['POST'])
@admin_required
def delete_logs():
    try:
        date_from = request.form.get('from')
        date_to = request.form.get('to')
        
        query = VisitLog.query
        
        if date_from:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(VisitLog.timestamp >= date_from_dt)
        
        if date_to:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(VisitLog.timestamp <= date_to_dt)
        
        count = query.count()
        query.delete()
        db.session.commit()
        
        flash(f'Successfully deleted {count} log records', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting logs: {str(e)}', 'danger')
    
    return redirect(url_for('view_logs'))

# ============ API ENDPOINTS ============

@app.route('/api/products')
def api_products():
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
        'whatsapp': p.whatsapp_number
    } for p in products])

@app.route('/api/stats')
@admin_required
def api_stats():
    stats = {
        'total_sellers': Seller.query.count(),
        'active_sellers': Seller.query.filter_by(is_active=True).count(),
        'total_products': Product.query.count(),
        'total_visits': VisitLog.query.count(),
        'today_visits': VisitLog.query.filter(
            VisitLog.timestamp >= datetime.utcnow().date()
        ).count()
    }
    return jsonify(stats)

# ============ ERROR HANDLERS ============

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# ============ MAIN ============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
