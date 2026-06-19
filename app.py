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
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'mcm_market_secret_key_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://mymarket_8q19_user:Hs2KnIFTlDPiz1vWfrPnLQ2dZUwhfN7B@dpg-d8i4gfmq1p3s73ebd8a0-a/mymarket_8q19'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
    'pool_recycle': 300,
    'pool_pre_ping': True,
}

# Image upload
UPLOAD_FOLDER = 'static/uploads'
PAYMENT_FOLDER = 'static/payments'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PAYMENT_FOLDER'] = PAYMENT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PAYMENT_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ============ DATABASE MODELS ============

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='seller')
    is_super_admin = db.Column(db.Boolean, default=False)
    shop_name = db.Column(db.String(100))
    whatsapp_number = db.Column(db.String(20))
    email = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    suspended_at = db.Column(db.DateTime, nullable=True)
    
    # Subscription fields - these are now safe because we added them manually
    subscription_status = db.Column(db.String(20), default='trial')
    trial_start = db.Column(db.DateTime, default=datetime.utcnow)
    trial_end = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=3))
    subscription_start = db.Column(db.DateTime, nullable=True)
    subscription_end = db.Column(db.DateTime, nullable=True)
    subscription_plan = db.Column(db.String(20), nullable=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def has_active_subscription(self):
        """Check if user has an active subscription or trial"""
        if self.role == 'admin':
            return True
        
        if self.subscription_status == 'trial':
            if self.trial_end and datetime.utcnow() <= self.trial_end:
                return True
            else:
                self.subscription_status = 'expired'
                try:
                    db.session.commit()
                except:
                    pass
                return False
        
        if self.subscription_status == 'active':
            if self.subscription_end and datetime.utcnow() <= self.subscription_end:
                return True
            else:
                self.subscription_status = 'expired'
                try:
                    db.session.commit()
                except:
                    pass
                return False
        
        return False
    
    def get_subscription_days_left(self):
        """Get days left in subscription or trial"""
        try:
            if self.subscription_status == 'trial' and self.trial_end:
                delta = self.trial_end - datetime.utcnow()
                return max(0, delta.days)
            elif self.subscription_status == 'active' and self.subscription_end:
                delta = self.subscription_end - datetime.utcnow()
                return max(0, delta.days)
        except:
            pass
        return 0

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    whatsapp_number = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    image_filename = db.Column(db.String(500))
    category = db.Column(db.String(50))
    is_available = db.Column(db.Boolean, default=True)
    
    seller = db.relationship('User', backref='products', foreign_keys=[seller_id])

class VisitLog(db.Model):
    __tablename__ = 'visit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50))
    heard_from = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_agent = db.Column(db.String(500))

class PaymentRequest(db.Model):
    __tablename__ = 'payment_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    plan = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_proof = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    seller = db.relationship('User', foreign_keys=[seller_id], backref='payment_requests')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])

# ============ CREATE TABLES ============

with app.app_context():
    db.create_all()
    print("✅ Database tables created!")
    
    # Create super admin if not exists
    if not User.query.filter_by(username='Mpc').first():
        admin = User(
            username='Mpc',
            role='admin',
            is_super_admin=True,
            is_active=True,
            subscription_status='active'
        )
        admin.set_password('08800Mpc!')
        db.session.add(admin)
        db.session.commit()
        print("✅ Super admin created!")
    
    # Update any existing sellers to have trial
    sellers = User.query.filter_by(role='seller').all()
    for seller in sellers:
        if not seller.trial_end:
            seller.trial_end = datetime.utcnow() + timedelta(days=3)
            seller.trial_start = datetime.utcnow()
            seller.subscription_status = 'trial'
    db.session.commit()
    print("✅ Database ready!")

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
        if current_user.role != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def seller_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please login first', 'danger')
            return redirect(url_for('login'))
        if current_user.role != 'seller':
            flash('Seller access required', 'danger')
            return redirect(url_for('index'))
        if not current_user.is_active:
            flash('Your account has been suspended', 'danger')
            return redirect(url_for('logout'))
        return f(*args, **kwargs)
    return decorated

def subscription_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please login first', 'danger')
            return redirect(url_for('login'))
        if current_user.role != 'seller':
            return f(*args, **kwargs)
        
        if not current_user.has_active_subscription():
            flash('Your subscription has expired. Please renew to continue.', 'warning')
            return redirect(url_for('subscription_page'))
        return f(*args, **kwargs)
    return decorated

# ============ ROUTES ============

@app.route('/')
def index():
    products = Product.query.filter_by(is_available=True).all()
    return render_template('index.html', products=products)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('seller_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash('Account suspended', 'danger')
                return render_template('login.html')
            
            login_user(user)
            flash(f'Welcome {user.username}!', 'success')
            
            if user.role == 'admin':
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
        ip_address=request.remote_addr,
        heard_from=heard,
        user_agent=request.headers.get('User-Agent', '')
    )
    db.session.add(log)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if query:
        products = Product.query.filter(
            Product.is_available == True,
            Product.name.ilike(f'%{query}%')
        ).all()
    else:
        products = Product.query.filter_by(is_available=True).all()
    return render_template('index.html', products=products, search_query=query)

# ============ SUBSCRIPTION ROUTES ============

@app.route('/subscription')
@seller_required
def subscription_page():
    seller = current_user
    plans = [
        {'id': 'monthly', 'name': '1 Month', 'price': 10, 'duration': 30},
        {'id': 'quarterly', 'name': '3 Months', 'price': 25, 'duration': 90},
        {'id': 'semiannual', 'name': '6 Months', 'price': 50, 'duration': 180},
        {'id': 'yearly', 'name': '1 Year', 'price': 100, 'duration': 365}
    ]
    
    payment_info = {
        'bank': 'MCM Bank',
        'account_name': 'MCM Market',
        'account_number': '1234567890',
        'mobile_money': '+256 123 456 789',
        'reference': f'MCM-{seller.id}-{datetime.now().strftime("%Y%m%d")}'
    }
    
    return render_template('subscription.html', 
                         seller=seller, 
                         plans=plans, 
                         payment_info=payment_info)

@app.route('/subscription/submit', methods=['POST'])
@seller_required
def submit_payment():
    seller = current_user
    plan = request.form.get('plan')
    
    plans = {
        'monthly': 10,
        'quarterly': 25,
        'semiannual': 50,
        'yearly': 100
    }
    
    if plan not in plans:
        flash('Invalid plan selected', 'danger')
        return redirect(url_for('subscription_page'))
    
    if 'payment_proof' not in request.files:
        flash('Please upload payment proof', 'danger')
        return redirect(url_for('subscription_page'))
    
    file = request.files['payment_proof']
    if file.filename == '':
        flash('Please select a file', 'danger')
        return redirect(url_for('subscription_page'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"payment_{seller.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
        filepath = os.path.join(app.config['PAYMENT_FOLDER'], filename)
        file.save(filepath)
        
        payment = PaymentRequest(
            seller_id=seller.id,
            plan=plan,
            amount=plans[plan],
            payment_proof=filename,
            status='pending'
        )
        db.session.add(payment)
        db.session.commit()
        
        flash('Payment submitted for review!', 'success')
        return redirect(url_for('seller_dashboard'))
    
    flash('Invalid file type', 'danger')
    return redirect(url_for('subscription_page'))

# ============ SELLER ROUTES ============

@app.route('/seller/dashboard')
@seller_required
def seller_dashboard():
    try:
        seller = current_user
        products = Product.query.filter_by(seller_id=seller.id).all()
        days_left = seller.get_subscription_days_left()
        has_active = seller.has_active_subscription()
        
        return render_template('seller_dashboard.html', 
                             seller=seller, 
                             products=products,
                             has_active=has_active,
                             days_left=days_left)
    except Exception as e:
        print(f"Error: {e}")
        return render_template('seller_dashboard.html', 
                             seller=current_user, 
                             products=[],
                             has_active=False,
                             days_left=0)

@app.route('/seller/product/add', methods=['GET', 'POST'])
@seller_required
@subscription_required
def seller_add_product():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            price = request.form.get('price')
            location = request.form.get('location')
            
            if not name or not price or not location:
                flash('All fields required', 'danger')
                return render_template('add_product.html', seller=current_user)
            
            product = Product(
                name=name,
                description=request.form.get('description'),
                price=float(price),
                location=location,
                seller_id=current_user.id,
                whatsapp_number=current_user.whatsapp_number,
                category=request.form.get('category')
            )
            
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    product.image_filename = filename
            
            db.session.add(product)
            db.session.commit()
            flash('Product uploaded!', 'success')
            return redirect(url_for('seller_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    
    return render_template('add_product.html', seller=current_user)

@app.route('/seller/product/<int:product_id>/delete')
@seller_required
@subscription_required
def seller_delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id == current_user.id:
        db.session.delete(product)
        db.session.commit()
        flash('Product deleted', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/seller/product/<int:product_id>/edit', methods=['GET', 'POST'])
@seller_required
@subscription_required
def seller_edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != current_user.id:
        flash('Unauthorized', 'danger')
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
                    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    product.image_filename = filename
            
            db.session.commit()
            flash('Product updated!', 'success')
            return redirect(url_for('seller_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    
    return render_template('edit_product.html', product=product, seller=current_user)

# ============ ADMIN ROUTES ============

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    sellers = User.query.filter_by(role='seller').all()
    admins = User.query.filter_by(role='admin').all()
    products = Product.query.all()
    logs = VisitLog.query.order_by(VisitLog.timestamp.desc()).limit(20).all()
    payments = PaymentRequest.query.order_by(PaymentRequest.created_at.desc()).all()
    
    stats = {
        'total_sellers': User.query.filter_by(role='seller').count(),
        'active_sellers': User.query.filter_by(role='seller', is_active=True).count(),
        'total_products': Product.query.count(),
        'total_visits': VisitLog.query.count(),
        'pending_payments': PaymentRequest.query.filter_by(status='pending').count()
    }
    
    return render_template('admin_dashboard.html', 
                         sellers=sellers, admins=admins, products=products,
                         logs=logs, payments=payments, **stats)

@app.route('/admin/seller/create', methods=['GET', 'POST'])
@admin_required
def create_seller():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        shop_name = request.form.get('shop_name')
        whatsapp = request.form.get('whatsapp')
        
        if User.query.filter_by(username=username).first():
            flash('Username exists', 'danger')
            return render_template('create_seller.html')
        
        seller = User(
            username=username,
            role='seller',
            shop_name=shop_name,
            whatsapp_number=whatsapp,
            email=request.form.get('email'),
            is_active=True,
            subscription_status='trial',
            trial_start=datetime.utcnow(),
            trial_end=datetime.utcnow() + timedelta(days=3)
        )
        seller.set_password(password)
        db.session.add(seller)
        db.session.commit()
        flash('Seller created with 3-day free trial!', 'success')
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
    seller.is_active = not seller.is_active
    if not seller.is_active:
        seller.suspended_at = datetime.utcnow()
    else:
        seller.suspended_at = None
    db.session.commit()
    flash(f'Seller {"suspended" if not seller.is_active else "activated"}', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/seller/<int:seller_id>/delete')
@admin_required
def delete_seller(seller_id):
    seller = User.query.get_or_404(seller_id)
    Product.query.filter_by(seller_id=seller_id).delete()
    db.session.delete(seller)
    db.session.commit()
    flash('Seller deleted', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/admin/create', methods=['GET', 'POST'])
@admin_required
def create_admin():
    if not current_user.is_super_admin:
        flash('Super admin required', 'danger')
        return redirect(url_for('admin_dashboard'))
    
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
            is_active=True,
            subscription_status='active'
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        flash('Admin created!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('create_admin.html')

@app.route('/admin/admin/<int:admin_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_admin(admin_id):
    if not current_user.is_super_admin:
        flash('Super admin required', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    admin = User.query.get_or_404(admin_id)
    
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
@admin_required
def delete_admin(admin_id):
    if not current_user.is_super_admin:
        flash('Super admin required', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    admin = User.query.get_or_404(admin_id)
    if admin.id == current_user.id:
        flash('Cannot delete yourself', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    db.session.delete(admin)
    db.session.commit()
    flash('Admin deleted', 'danger')
    return redirect(url_for('admin_dashboard'))

# ============ PAYMENT MANAGEMENT ============

@app.route('/admin/payments')
@admin_required
def manage_payments():
    payments = PaymentRequest.query.order_by(PaymentRequest.created_at.desc()).all()
    return render_template('manage_payments.html', payments=payments)

@app.route('/admin/payment/<int:payment_id>/approve', methods=['POST'])
@admin_required
def approve_payment(payment_id):
    payment = PaymentRequest.query.get_or_404(payment_id)
    seller = User.query.get(payment.seller_id)
    
    if seller:
        plan_durations = {
            'monthly': 30,
            'quarterly': 90,
            'semiannual': 180,
            'yearly': 365
        }
        
        duration = plan_durations.get(payment.plan, 30)
        seller.subscription_status = 'active'
        seller.subscription_start = datetime.utcnow()
        seller.subscription_end = datetime.utcnow() + timedelta(days=duration)
        seller.subscription_plan = payment.plan
        
        payment.status = 'approved'
        payment.reviewed_at = datetime.utcnow()
        payment.reviewed_by = current_user.id
        
        db.session.commit()
        flash('Payment approved! Subscription activated.', 'success')
    else:
        flash('Seller not found', 'danger')
    
    return redirect(url_for('manage_payments'))

@app.route('/admin/payment/<int:payment_id>/deny', methods=['POST'])
@admin_required
def deny_payment(payment_id):
    payment = PaymentRequest.query.get_or_404(payment_id)
    payment.status = 'denied'
    payment.reviewed_at = datetime.utcnow()
    payment.reviewed_by = current_user.id
    payment.notes = request.form.get('notes', 'Payment verification failed.')
    
    db.session.commit()
    flash('Payment denied.', 'warning')
    return redirect(url_for('manage_payments'))

# ============ LOGS ============

@app.route('/admin/logs')
@admin_required
def view_logs():
    logs = VisitLog.query.order_by(VisitLog.timestamp.desc()).all()
    stats = {
        'total': VisitLog.query.count(),
        'internet': VisitLog.query.filter_by(heard_from='Internet').count(),
        'friend': VisitLog.query.filter_by(heard_from='Friend').count(),
        'research': VisitLog.query.filter_by(heard_from='Self Research').count()
    }
    return render_template('logs.html', logs=logs, stats=stats)

@app.route('/admin/logs/download')
@admin_required
def download_logs():
    logs = VisitLog.query.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'IP', 'Heard From', 'Timestamp'])
    for log in logs:
        writer.writerow([log.id, log.ip_address, log.heard_from, log.timestamp])
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
