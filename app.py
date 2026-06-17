from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import csv
import io
from functools import wraps
from PIL import Image
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mcm_market_secret_key_2026')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///mcm_market.db')
if app.config['SQLALCHEMY_DATABASE_URI'] and app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
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

# ============ MODELS ============

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

# ============ CREATE TABLES ============

with app.app_context():
    try:
        db.create_all()
        print("✅ Database tables created!")
        
        # Create super admin if not exists
        if not User.query.filter_by(username='Mpc', role='admin').first():
            admin = User(
                username='Mpc',
                role='admin',
                is_super_admin=True,
                is_active=True
            )
            admin.set_password(os.environ.get('ADMIN_PASSWORD', '08800Mpc!'))
            db.session.add(admin)
            db.session.commit()
            print("✅ Super admin created!")
    except Exception as e:
        print(f"⚠️ Database init warning: {e}")

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
    products = Product.query.filter(
        Product.is_available == True,
        Product.seller.has(is_active=True)
    ).order_by(Product.created_at.desc()).all()
    return render_template('index.html', products=products)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard' if current_user.is_admin() else 'seller_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'seller')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash('Account suspended. Contact admin.', 'danger')
                return render_template('login.html')
            
            login_user(user)
            flash(f'Welcome {user.username}!', 'success')
            
            if user.is_admin():
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('seller_dashboard'))
        
        flash('Invalid credentials', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    flash('Logged out', 'success')
    return redirect(url_for('index'))

@app.route('/heard_from', methods=['POST'])
def heard_from():
    heard = request.form.get('heard_from')
    log = VisitLog(
        ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
        heard_from=heard,
        user_agent=request.headers.get('User-Agent', '')[:500]
    )
    db.session.add(log)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    products = Product.query.filter(
        Product.is_available == True,
        Product.seller.has(is_active=True)
    )
    if query:
        products = products.filter(
            Product.name.contains(query) | Product.description.contains(query)
        )
    return render_template('index.html', products=products.all(), search_query=query)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('product_detail.html', product=product)

# ============ SELLER ROUTES ============

@app.route('/seller/dashboard')
@seller_required
def seller_dashboard():
    seller = current_user
    products = Product.query.filter_by(seller_id=seller.id).order_by(Product.created_at.desc()).all()
    return render_template('seller_dashboard.html', seller=seller, products=products)

@app.route('/seller/product/add', methods=['GET', 'POST'])
@seller_required
def seller_add_product():
    seller = current_user
    
    if request.method == 'POST':
        name = request.form.get('name')
        price = request.form.get('price')
        location = request.form.get('location')
        
        if not name or not price or not location:
            flash('Name, Price, and Location are required', 'danger')
            return render_template('add_product.html', seller=seller)
        
        try:
            price = float(price)
        except:
            flash('Invalid price', 'danger')
            return render_template('add_product.html', seller=seller)
        
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
        flash('Product uploaded!', 'success')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('add_product.html', seller=seller)

@app.route('/seller/product/<int:product_id>/delete')
@seller_required
def seller_delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('seller_dashboard'))
    
    if product.image_filename:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], product.image_filename))
        except:
            pass
    
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/seller/product/<int:product_id>/edit', methods=['GET', 'POST'])
@seller_required
def seller_edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('seller_dashboard'))
    
    if request.method == 'POST':
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
        flash('Product updated!', 'success')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('edit_product.html', product=product, seller=current_user)

# ============ ADMIN ROUTES ============

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
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

@app.route('/admin/seller/create', methods=['GET', 'POST'])
@admin_required
def create_seller():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        shop_name = request.form.get('shop_name')
        whatsapp = request.form.get('whatsapp')
        
        if not all([username, password, shop_name, whatsapp]):
            flash('All fields required', 'danger')
            return render_template('create_seller.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username exists', 'danger')
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
        flash('Seller created!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('create_seller.html')

@app.route('/admin/seller/<int:seller_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_seller(seller_id):
    seller = User.query.get_or_404(seller_id)
    
    if request.method == 'POST':
        seller.shop_name = request.form.get('shop_name')
        seller.whatsapp_number = request.form.get('whatsapp')
        seller.email = request.form.get('email')
        if request.form.get('password'):
            seller.set_password(request.form.get('password'))
        db.session.commit()
        flash('Seller updated!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('edit_seller.html', seller=seller)

@app.route('/admin/seller/<int:seller_id>/toggle')
@admin_required
def toggle_seller(seller_id):
    seller = User.query.get_or_404(seller_id)
    if seller.is_active:
        seller.suspend()
        flash('Seller suspended', 'warning')
    else:
        seller.unsuspend()
        flash('Seller unsuspended', 'success')
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/seller/<int:seller_id>/delete')
@admin_required
def delete_seller(seller_id):
    seller = User.query.get_or_404(seller_id)
    for product in seller.products:
        if product.image_filename:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], product.image_filename))
            except:
                pass
    db.session.delete(seller)
    db.session.commit()
    flash('Seller deleted', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/admin/create', methods=['GET', 'POST'])
@super_admin_required
def create_admin():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        is_super = request.form.get('is_super') == 'on'
        
        if User.query.filter_by(username=username).first():
            flash('Username exists', 'danger')
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
        flash('Admin created!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('create_admin.html')

@app.route('/admin/admin/<int:admin_id>/edit', methods=['GET', 'POST'])
@super_admin_required
def edit_admin(admin_id):
    admin = User.query.get_or_404(admin_id)
    if admin.id == current_user.id:
        flash('Cannot edit yourself here', 'info')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        admin.username = request.form.get('username')
        if request.form.get('password'):
            admin.set_password(request.form.get('password'))
        admin.is_super_admin = request.form.get('is_super') == 'on'
        db.session.commit()
        flash('Admin updated!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('edit_admin.html', admin=admin)

@app.route('/admin/admin/<int:admin_id>/delete')
@super_admin_required
def delete_admin(admin_id):
    admin = User.query.get_or_404(admin_id)
    if admin.id == current_user.id:
        flash('Cannot delete yourself', 'danger')
        return redirect(url_for('admin_dashboard'))
    db.session.delete(admin)
    db.session.commit()
    flash('Admin deleted', 'danger')
    return redirect(url_for('admin_dashboard'))

# ============ LOGS ============

@app.route('/admin/logs')
@admin_required
def view_logs():
    logs = VisitLog.query.order_by(VisitLog.timestamp.desc()).all()
    return render_template('logs.html', logs=logs)

@app.route('/admin/logs/download')
@admin_required
def download_logs():
    logs = VisitLog.query.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'IP', 'Heard From', 'Timestamp', 'User Agent'])
    for log in logs:
        writer.writerow([log.id, log.ip_address, log.heard_from, log.timestamp, log.user_agent])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'logs_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@app.route('/admin/logs/delete', methods=['POST'])
@admin_required
def delete_logs():
    VisitLog.query.delete()
    db.session.commit()
    flash('Logs deleted', 'success')
    return redirect(url_for('view_logs'))

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
