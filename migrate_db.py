from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os
import sqlite3

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mcm_market.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Old models for migration
class OldAdmin(db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    password_hash = db.Column(db.String(200))
    is_super_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime)

class OldSeller(db.Model):
    __tablename__ = 'sellers'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    password_hash = db.Column(db.String(200))
    shop_name = db.Column(db.String(100))
    whatsapp_number = db.Column(db.String(20))
    email = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime)
    suspended_at = db.Column(db.DateTime)

class OldProduct(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    description = db.Column(db.Text)
    price = db.Column(db.Float)
    location = db.Column(db.String(200))
    seller_id = db.Column(db.Integer)
    whatsapp_number = db.Column(db.String(20))
    created_at = db.Column(db.DateTime)
    image_url = db.Column(db.String(500))
    category = db.Column(db.String(50))
    is_available = db.Column(db.Boolean, default=True)

class OldVisitLog(db.Model):
    __tablename__ = 'visit_logs'
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50))
    heard_from = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime)
    user_agent = db.Column(db.String(500))
    session_id = db.Column(db.String(100))
    referer = db.Column(db.String(200))

def migrate():
    with app.app_context():
        try:
            # Check if old tables exist
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'admins' in tables and 'sellers' in tables:
                print("📦 Migrating data from old tables to new unified users table...")
                
                # Get old data
                old_admins = OldAdmin.query.all()
                old_sellers = OldSeller.query.all()
                
                # Import new User model
                from app import User, Product, VisitLog
                
                # Migrate admins
                for old_admin in old_admins:
                    user = User(
                        username=old_admin.username,
                        password_hash=old_admin.password_hash,
                        role='admin',
                        is_super_admin=old_admin.is_super_admin,
                        created_at=old_admin.created_at,
                        is_active=True
                    )
                    db.session.add(user)
                
                # Migrate sellers
                for old_seller in old_sellers:
                    user = User(
                        username=old_seller.username,
                        password_hash=old_seller.password_hash,
                        role='seller',
                        shop_name=old_seller.shop_name,
                        whatsapp_number=old_seller.whatsapp_number,
                        email=old_seller.email,
                        is_active=old_seller.is_active,
                        created_at=old_seller.created_at,
                        suspended_at=old_seller.suspended_at
                    )
                    db.session.add(user)
                
                db.session.commit()
                print("✅ Data migration completed!")
                
                # Drop old tables
                print("🗑️ Dropping old tables...")
                db.drop_all()
                print("✅ Old tables dropped!")
                
                # Recreate all tables with new schema
                print("🔄 Creating new tables...")
                db.create_all()
                print("✅ New tables created!")
                
            else:
                print("ℹ️ No old tables found. Creating fresh database...")
                db.create_all()
                print("✅ Database created!")
                
        except Exception as e:
            print(f"❌ Migration error: {e}")
            db.session.rollback()

if __name__ == '__main__':
    migrate()
