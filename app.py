from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
import sqlite3
import os
from functools import wraps
import hashlib

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-this-2024'

# Ensure uploads directory exists
os.makedirs('static/uploads/proofs', exist_ok=True)

def init_db():
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    # Sellers table
    c.execute('''CREATE TABLE IF NOT EXISTS sellers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_name TEXT NOT NULL,
        owner_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT NOT NULL,
        whatsapp TEXT NOT NULL,
        password TEXT NOT NULL,
        trial_start DATE NOT NULL,
        trial_end DATE NOT NULL,
        subscription_end DATE,
        is_paid BOOLEAN DEFAULT 0,
        is_active BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Products table
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        product_name TEXT NOT NULL,
        price REAL NOT NULL,
        description TEXT,
        location TEXT NOT NULL,
        whatsapp TEXT NOT NULL,
        image_url TEXT,
        category TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (seller_id) REFERENCES sellers (id)
    )''')
    
    # Buyers table
    c.execute('''CREATE TABLE IF NOT EXISTS buyers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Subscription requests table
    c.execute('''CREATE TABLE IF NOT EXISTS subscription_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        plan TEXT NOT NULL,
        amount REAL NOT NULL,
        months INTEGER NOT NULL,
        proof_image TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (seller_id) REFERENCES sellers (id)
    )''')
    
    # Bank account settings
    c.execute('''CREATE TABLE IF NOT EXISTS bank_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bank_name TEXT,
        account_name TEXT,
        account_number TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Insert default bank account
    c.execute("SELECT * FROM bank_settings")
    if not c.fetchone():
        c.execute("INSERT INTO bank_settings (bank_name, account_name, account_number) VALUES (?, ?, ?)",
                  ('Bank Name Here', 'Account Holder Name', 'Account Number Here'))
    
    # Insert owner account
    c.execute("SELECT * FROM sellers WHERE email = 'owner@mymarketplace.com'")
    if not c.fetchone():
        c.execute('''INSERT INTO sellers (business_name, owner_name, email, phone, whatsapp, password, trial_start, trial_end, is_paid)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        ('Market Owner', 'Admin', 'owner@mymarketplace.com', '0000000000', '0000000000', 
         hashlib.sha256('0880Owner+_+'.encode()).hexdigest(),
         datetime.now().date(), datetime.now().date() + timedelta(days=3650), 1))
    
    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def seller_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_type') != 'seller':
            flash('Seller access required', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def owner_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_type') != 'owner':
            flash('Owner access only', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    today = datetime.now().date()
    products = c.execute('''SELECT p.*, s.business_name, s.whatsapp as seller_whatsapp 
        FROM products p 
        JOIN sellers s ON p.seller_id = s.id 
        WHERE s.is_active = 1 AND s.is_paid = 1
        ORDER BY p.created_at DESC LIMIT 30''', (today,)).fetchall()
    
    conn.close()
    return render_template('index.html', products=products)

@app.route('/register/seller', methods=['GET', 'POST'])
def register_seller():
    if request.method == 'POST':
        business_name = request.form['business_name']
        owner_name = request.form['owner_name']
        email = request.form['email']
        phone = request.form['phone']
        whatsapp = request.form['whatsapp']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        
        trial_start = datetime.now().date()
        trial_end = trial_start + timedelta(days=10)
        
        conn = sqlite3.connect('marketplace.db')
        c = conn.cursor()
        
        try:
            c.execute('''INSERT INTO sellers (business_name, owner_name, email, phone, whatsapp, password, trial_start, trial_end, is_paid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (business_name, owner_name, email, phone, whatsapp, password, trial_start, trial_end, 0))
            conn.commit()
            flash('Registration successful! You have 10 days free trial. You can add products during trial. After trial, you must subscribe to continue.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already registered', 'danger')
        finally:
            conn.close()
    
    return render_template('register_seller.html')

@app.route('/register/buyer', methods=['GET', 'POST'])
def register_buyer():
    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        phone = request.form['phone']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        
        conn = sqlite3.connect('marketplace.db')
        c = conn.cursor()
        
        try:
            c.execute('INSERT INTO buyers (full_name, email, phone, password) VALUES (?, ?, ?, ?)',
                     (full_name, email, phone, password))
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already registered', 'danger')
        finally:
            conn.close()
    
    return render_template('register_buyer.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        user_type = request.form['user_type']
        
        conn = sqlite3.connect('marketplace.db')
        c = conn.cursor()
        
        if user_type == 'owner':
            c.execute("SELECT * FROM sellers WHERE email = 'owner@mymarketplace.com'")
            user = c.fetchone()
            if user and password == hashlib.sha256('0880Owner+_+'.encode()).hexdigest():
                session['user_id'] = user[0]
                session['user_type'] = 'owner'
                session['user_name'] = 'Owner'
                flash('Welcome Owner!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid owner credentials', 'danger')
        
        elif user_type == 'seller':
            c.execute("SELECT * FROM sellers WHERE email = ? AND password = ?", (email, password))
            user = c.fetchone()
            if user:
                session['user_id'] = user[0]
                session['user_type'] = 'seller'
                session['user_name'] = user[1]
                flash(f'Welcome {user[1]}!', 'success')
                return redirect(url_for('seller_dashboard'))
            else:
                flash('Invalid email or password', 'danger')
        
        elif user_type == 'buyer':
            c.execute("SELECT * FROM buyers WHERE email = ? AND password = ?", (email, password))
            user = c.fetchone()
            if user:
                session['user_id'] = user[0]
                session['user_type'] = 'buyer'
                session['user_name'] = user[1]
                flash(f'Welcome {user[1]}!', 'success')
                return redirect(url_for('buyer_dashboard'))
            else:
                flash('Invalid email or password', 'danger')
        
        conn.close()
    
    return render_template('login.html')

@app.route('/seller/dashboard')
@seller_required
def seller_dashboard():
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    seller = c.execute("SELECT * FROM sellers WHERE id = ?", (session['user_id'],)).fetchone()
    products = c.execute("SELECT * FROM products WHERE seller_id = ? ORDER BY created_at DESC", (session['user_id'],)).fetchall()
    
    today = datetime.now().date()
    trial_end = datetime.strptime(seller[7], '%Y-%m-%d').date() if isinstance(seller[7], str) else seller[7]
    trial_days_left = (trial_end - today).days if trial_end >= today else 0
    
    # Check subscription status
    is_subscribed = seller[9] == 1
    subscription_end = datetime.strptime(seller[8], '%Y-%m-%d').date() if seller[8] and isinstance(seller[8], str) else seller[8] if seller[8] else None
    
    # Get pending subscription request
    pending_request = c.execute("SELECT * FROM subscription_requests WHERE seller_id = ? AND status = 'pending'", (session['user_id'],)).fetchone()
    
    conn.close()
    
    return render_template('seller_dashboard.html', 
                         seller=seller, 
                         products=products, 
                         trial_days_left=trial_days_left,
                         is_subscribed=is_subscribed,
                         subscription_end=subscription_end,
                         pending_request=pending_request)

@app.route('/seller/subscribe', methods=['GET', 'POST'])
@seller_required
def subscribe():
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        plan = request.form['plan']
        amount = float(request.form['amount'])
        months = int(request.form['months'])
        
        if 'proof_image' not in request.files:
            flash('Please upload payment proof', 'danger')
            return redirect(url_for('subscribe'))
        
        file = request.files['proof_image']
        if file.filename == '':
            flash('Please select a file', 'danger')
            return redirect(url_for('subscribe'))
        
        # Save file
        filename = f"proof_{session['user_id']}_{datetime.now().timestamp()}.jpg"
        filepath = os.path.join('static/uploads/proofs', filename)
        file.save(filepath)
        
        c.execute('''INSERT INTO subscription_requests (seller_id, plan, amount, months, proof_image, status)
        VALUES (?, ?, ?, ?, ?, 'pending')''', (session['user_id'], plan, amount, months, filename))
        conn.commit()
        
        flash('Subscription request sent! Admin will verify and activate your subscription.', 'success')
        return redirect(url_for('seller_dashboard'))
    
    # Get bank details
    bank = c.execute("SELECT * FROM bank_settings LIMIT 1").fetchone()
    conn.close()
    
    plans = [
        {'name': '1 Month', 'months': 1, 'price': 10},
        {'name': '3 Months', 'months': 3, 'price': 20},
        {'name': '6 Months', 'months': 6, 'price': 35},
        {'name': '12 Months', 'months': 12, 'price': 50}
    ]
    
    return render_template('subscribe.html', bank=bank, plans=plans)

@app.route('/seller/add_product', methods=['GET', 'POST'])
@seller_required
def add_product():
    if request.method == 'POST':
        product_name = request.form['product_name']
        price = float(request.form['price'])
        description = request.form['description']
        location = request.form['location']
        whatsapp = request.form['whatsapp']
        category = request.form.get('category', 'General')
        
        conn = sqlite3.connect('marketplace.db')
        c = conn.cursor()
        c.execute('''INSERT INTO products (seller_id, product_name, price, description, location, whatsapp, category)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (session['user_id'], product_name, price, description, location, whatsapp, category))
        conn.commit()
        conn.close()
        
        flash('Product added successfully!', 'success')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('add_product.html')

@app.route('/seller/delete_product/<int:product_id>')
@seller_required
def delete_product(product_id):
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ? AND seller_id = ?", (product_id, session['user_id']))
    conn.commit()
    conn.close()
    flash('Product deleted', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/buyer/dashboard')
def buyer_dashboard():
    if session.get('user_type') != 'buyer':
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    products = c.execute('''SELECT p.*, s.business_name, s.whatsapp as seller_whatsapp 
        FROM products p 
        JOIN sellers s ON p.seller_id = s.id 
        WHERE s.is_active = 1 AND s.is_paid = 1
        ORDER BY p.created_at DESC''').fetchall()
    
    conn.close()
    return render_template('buyer_dashboard.html', products=products)

@app.route('/admin/dashboard')
@owner_required
def admin_dashboard():
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    sellers = c.execute("SELECT * FROM sellers WHERE email != 'owner@mymarketplace.com' ORDER BY created_at DESC").fetchall()
    products = c.execute("SELECT p.*, s.business_name FROM products p JOIN sellers s ON p.seller_id = s.id ORDER BY p.created_at DESC LIMIT 50").fetchall()
    buyers = c.execute("SELECT * FROM buyers ORDER BY created_at DESC").fetchall()
    subscription_requests = c.execute('''SELECT r.*, s.business_name, s.email 
        FROM subscription_requests r 
        JOIN sellers s ON r.seller_id = s.id 
        WHERE r.status = 'pending'
        ORDER BY r.created_at DESC''').fetchall()
    bank = c.execute("SELECT * FROM bank_settings LIMIT 1").fetchone()
    
    today = datetime.now().date()
    stats = {
        'total_sellers': len(sellers),
        'total_products': c.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        'total_buyers': len(buyers),
        'pending_requests': len(subscription_requests)
    }
    
    conn.close()
    return render_template('admin_dashboard.html', 
                         sellers=sellers, 
                         products=products, 
                         buyers=buyers,
                         subscription_requests=subscription_requests,
                         bank=bank,
                         stats=stats)

@app.route('/admin/approve_subscription/<int:request_id>')
@owner_required
def approve_subscription(request_id):
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    # Get request details
    req = c.execute("SELECT * FROM subscription_requests WHERE id = ?", (request_id,)).fetchone()
    if req:
        seller_id = req[1]
        months = req[4]
        
        # Update subscription
        subscription_end = datetime.now().date() + timedelta(days=30 * months)
        c.execute("UPDATE sellers SET is_paid = 1, subscription_end = ? WHERE id = ?", (subscription_end, seller_id))
        c.execute("UPDATE subscription_requests SET status = 'approved' WHERE id = ?", (request_id,))
        conn.commit()
        flash('Subscription approved! Seller can now list products.', 'success')
    
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject_subscription/<int:request_id>')
@owner_required
def reject_subscription(request_id):
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    c.execute("UPDATE subscription_requests SET status = 'rejected' WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()
    flash('Subscription rejected', 'warning')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update_bank', methods=['POST'])
@owner_required
def update_bank():
    bank_name = request.form['bank_name']
    account_name = request.form['account_name']
    account_number = request.form['account_number']
    
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    c.execute("UPDATE bank_settings SET bank_name = ?, account_name = ?, account_number = ?, updated_at = CURRENT_TIMESTAMP", 
              (bank_name, account_name, account_number))
    conn.commit()
    conn.close()
    
    flash('Bank details updated!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/toggle_seller/<int:seller_id>')
@owner_required
def toggle_seller(seller_id):
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    c.execute("UPDATE sellers SET is_active = NOT is_active WHERE id = ?", (seller_id,))
    conn.commit()
    conn.close()
    flash('Seller status updated', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_product/<int:product_id>')
@owner_required
def delete_product(product_id):
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    flash('Product deleted', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
