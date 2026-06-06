from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
import os
from functools import wraps
import hashlib
import psycopg2
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-this-2024'
app.config['UPLOAD_FOLDER'] = 'static/uploads/products'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/uploads/proofs', exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://mymarket_8q19_user:Hs2KnIFTlDPiz1vWfrPnLQ2dZUwhfN7B@dpg-d8i4gfmq1p3s73ebd8a0-a/mymarket_8q19')

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS sellers (
        id SERIAL PRIMARY KEY,
        business_name TEXT NOT NULL,
        owner_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT NOT NULL,
        whatsapp TEXT NOT NULL,
        password TEXT NOT NULL,
        trial_start DATE NOT NULL,
        trial_end DATE NOT NULL,
        subscription_end DATE,
        is_paid BOOLEAN DEFAULT FALSE,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        seller_id INTEGER NOT NULL REFERENCES sellers(id),
        product_name TEXT NOT NULL,
        price REAL NOT NULL,
        description TEXT,
        location TEXT NOT NULL,
        whatsapp TEXT NOT NULL,
        image_url TEXT,
        category TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS buyers (
        id SERIAL PRIMARY KEY,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS subscription_requests (
        id SERIAL PRIMARY KEY,
        seller_id INTEGER NOT NULL REFERENCES sellers(id),
        plan TEXT NOT NULL,
        amount REAL NOT NULL,
        months INTEGER NOT NULL,
        proof_image TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bank_settings (
        id SERIAL PRIMARY KEY,
        bank_name TEXT,
        account_name TEXT,
        account_number TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    
    c.execute("SELECT * FROM bank_settings")
    if not c.fetchone():
        c.execute("INSERT INTO bank_settings (bank_name, account_name, account_number) VALUES (%s, %s, %s)",
                  ('Bank Name Here', 'Account Holder Name', 'Account Number Here'))
        conn.commit()
    
    c.execute("SELECT * FROM sellers WHERE email = 'owner@mymarketplace.com'")
    if not c.fetchone():
        hashed_password = hashlib.sha256('0880Owner+_+'.encode()).hexdigest()
        c.execute('''INSERT INTO sellers (business_name, owner_name, email, phone, whatsapp, password, trial_start, trial_end, is_paid)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
        ('Market Owner', 'Admin', 'owner@mymarketplace.com', '0000000000', '0000000000', 
         hashed_password, datetime.now().date(), datetime.now().date() + timedelta(days=3650), True))
        conn.commit()
    
    conn.close()
    print("Database initialized!")

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
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def owner_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_type') != 'owner':
            flash('Owner access only', 'danger')
            return redirect(url_for('owner_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    conn = get_db()
    c = conn.cursor()
    
    try:
        # Show products from sellers who are:
        # 1. Active AND (paid OR still on trial)
        today = datetime.now().date()
        c.execute('''SELECT p.*, s.business_name, s.whatsapp as seller_whatsapp 
            FROM products p 
            JOIN sellers s ON p.seller_id = s.id 
            WHERE s.is_active = TRUE 
            AND (s.is_paid = TRUE OR s.trial_end >= %s)
            ORDER BY p.created_at DESC LIMIT 12''', (today,))
        products = c.fetchall()
    except Exception as e:
        products = []
        print(f"Error: {e}")
    
    conn.close()
    return render_template('index.html', products=products)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')
    location = request.args.get('location', '')
    
    conn = get_db()
    c = conn.cursor()
    
    today = datetime.now().date()
    sql = '''SELECT p.*, s.business_name, s.whatsapp as seller_whatsapp 
        FROM products p 
        JOIN sellers s ON p.seller_id = s.id 
        WHERE s.is_active = TRUE 
        AND (s.is_paid = TRUE OR s.trial_end >= %s)'''
    params = [today]
    
    if query:
        sql += " AND (p.product_name ILIKE %s OR p.description ILIKE %s)"
        params.extend([f'%{query}%', f'%{query}%'])
    
    if category:
        sql += " AND p.category = %s"
        params.append(category)
    
    if min_price:
        sql += " AND p.price >= %s"
        params.append(float(min_price))
    
    if max_price:
        sql += " AND p.price <= %s"
        params.append(float(max_price))
    
    if location:
        sql += " AND p.location ILIKE %s"
        params.append(f'%{location}%')
    
    sql += " ORDER BY p.created_at DESC"
    
    c.execute(sql, params)
    products = c.fetchall()
    
    c.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL")
    categories = [row[0] for row in c.fetchall()]
    
    conn.close()
    
    return render_template('search.html', products=products, query=query, 
                         category=category, min_price=min_price, max_price=max_price,
                         location=location, categories=categories)

@app.route('/owner/login', methods=['GET', 'POST'])
def owner_login():
    if request.method == 'POST':
        email = request.form['email']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM sellers WHERE email = 'owner@mymarketplace.com'")
        user = c.fetchone()
        conn.close()
        
        if user and password == hashlib.sha256('0880Owner+_+'.encode()).hexdigest():
            session['user_id'] = user[0]
            session['user_type'] = 'owner'
            session['user_name'] = 'Owner'
            flash('Welcome Owner!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid owner credentials', 'danger')
    
    return render_template('owner_login.html')

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
        
        conn = get_db()
        c = conn.cursor()
        
        try:
            c.execute('''INSERT INTO sellers (business_name, owner_name, email, phone, whatsapp, password, trial_start, trial_end, is_paid)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (business_name, owner_name, email, phone, whatsapp, password, trial_start, trial_end, False))
            conn.commit()
            flash('Registration successful! You have 10 days free trial. Your products will be visible to buyers during trial. After trial ends, subscribe to continue.', 'success')
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            flash('Email already registered', 'danger')
            conn.rollback()
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
        
        conn = get_db()
        c = conn.cursor()
        
        try:
            c.execute('INSERT INTO buyers (full_name, email, phone, password) VALUES (%s, %s, %s, %s)',
                     (full_name, email, phone, password))
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            flash('Email already registered', 'danger')
            conn.rollback()
        finally:
            conn.close()
    
    return render_template('register_buyer.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        user_type = request.form['user_type']
        
        conn = get_db()
        c = conn.cursor()
        
        if user_type == 'seller':
            c.execute("SELECT * FROM sellers WHERE email = %s AND password = %s", (email, password))
            user = c.fetchone()
            if user and user[3] != 'owner@mymarketplace.com':
                session['user_id'] = user[0]
                session['user_type'] = 'seller'
                session['user_name'] = user[1]
                flash(f'Welcome {user[1]}!', 'success')
                conn.close()
                return redirect(url_for('seller_dashboard'))
            else:
                flash('Invalid email or password', 'danger')
        
        elif user_type == 'buyer':
            c.execute("SELECT * FROM buyers WHERE email = %s AND password = %s", (email, password))
            user = c.fetchone()
            if user:
                session['user_id'] = user[0]
                session['user_type'] = 'buyer'
                session['user_name'] = user[1]
                flash(f'Welcome {user[1]}!', 'success')
                conn.close()
                return redirect(url_for('buyer_dashboard'))
            else:
                flash('Invalid email or password', 'danger')
        
        conn.close()
    
    return render_template('login.html')

@app.route('/seller/dashboard')
@seller_required
def seller_dashboard():
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM sellers WHERE id = %s", (session['user_id'],))
    seller = c.fetchone()
    
    c.execute("SELECT p.* FROM products p WHERE p.seller_id = %s ORDER BY p.created_at DESC", (session['user_id'],))
    products = c.fetchall()
    
    today = datetime.now().date()
    trial_start = seller[7]
    trial_end = seller[8]
    is_paid = seller[9]
    
    trial_days_left = (trial_end - today).days if trial_end >= today else 0
    is_on_trial = trial_days_left > 0 and not is_paid
    is_subscribed = is_paid
    
    # Check if products are visible to buyers
    products_visible = is_subscribed or is_on_trial
    
    c.execute("SELECT * FROM subscription_requests WHERE seller_id = %s AND status = 'pending'", (session['user_id'],))
    pending_request = c.fetchone()
    
    conn.close()
    
    return render_template('seller_dashboard.html', 
                         seller=seller, 
                         products=products, 
                         trial_days_left=trial_days_left,
                         is_on_trial=is_on_trial,
                         is_subscribed=is_subscribed,
                         products_visible=products_visible,
                         pending_request=pending_request)

@app.route('/seller/subscribe', methods=['GET', 'POST'])
@seller_required
def subscribe():
    conn = get_db()
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
        
        filename = secure_filename(f"proof_{session['user_id']}_{int(datetime.now().timestamp())}.jpg")
        filepath = os.path.join('static/uploads/proofs', filename)
        file.save(filepath)
        
        c.execute('''INSERT INTO subscription_requests (seller_id, plan, amount, months, proof_image, status)
        VALUES (%s, %s, %s, %s, %s, 'pending')''', (session['user_id'], plan, amount, months, filename))
        conn.commit()
        
        flash('Subscription request sent! Admin will verify. Once approved, your products will remain visible after trial ends.', 'success')
        return redirect(url_for('seller_dashboard'))
    
    c.execute("SELECT * FROM bank_settings LIMIT 1")
    bank = c.fetchone()
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
        
        image_url = None
        if 'product_image' in request.files:
            file = request.files['product_image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"product_{session['user_id']}_{int(datetime.now().timestamp())}.{file.filename.rsplit('.', 1)[1].lower()}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_url = f"/static/uploads/products/{filename}"
        
        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO products (seller_id, product_name, price, description, location, whatsapp, category, image_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
        (session['user_id'], product_name, price, description, location, whatsapp, category, image_url))
        conn.commit()
        conn.close()
        
        flash('Product added successfully!', 'success')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('add_product.html')

@app.route('/seller/delete_product/<int:product_id>')
@seller_required
def seller_delete_product(product_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = %s AND seller_id = %s", (product_id, session['user_id']))
    conn.commit()
    conn.close()
    flash('Product deleted', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/buyer/dashboard')
def buyer_dashboard():
    if session.get('user_type') != 'buyer':
        flash('Please login as buyer first', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db()
    c = conn.cursor()
    
    today = datetime.now().date()
    c.execute('''SELECT p.*, s.business_name 
        FROM products p 
        JOIN sellers s ON p.seller_id = s.id 
        WHERE s.is_active = TRUE 
        AND (s.is_paid = TRUE OR s.trial_end >= %s)
        ORDER BY p.created_at DESC''', (today,))
    products = c.fetchall()
    
    conn.close()
    return render_template('buyer_dashboard.html', products=products)

@app.route('/admin/dashboard')
@owner_required
def admin_dashboard():
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM sellers WHERE email != 'owner@mymarketplace.com' ORDER BY created_at DESC")
    sellers = c.fetchall()
    
    c.execute("SELECT p.*, s.business_name FROM products p JOIN sellers s ON p.seller_id = s.id ORDER BY p.created_at DESC LIMIT 50")
    products = c.fetchall()
    
    c.execute("SELECT * FROM buyers ORDER BY created_at DESC")
    buyers = c.fetchall()
    
    c.execute('''SELECT r.*, s.business_name, s.email 
        FROM subscription_requests r 
        JOIN sellers s ON r.seller_id = s.id 
        WHERE r.status = 'pending'
        ORDER BY r.created_at DESC''')
    subscription_requests = c.fetchall()
    
    c.execute("SELECT * FROM bank_settings LIMIT 1")
    bank = c.fetchone()
    
    c.execute("SELECT COUNT(*) FROM products")
    total_products = c.fetchone()[0]
    
    stats = {
        'total_sellers': len(sellers),
        'total_products': total_products,
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
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM subscription_requests WHERE id = %s", (request_id,))
    req = c.fetchone()
    if req:
        seller_id = req[1]
        months = req[4]
        
        subscription_end = datetime.now().date() + timedelta(days=30 * months)
        c.execute("UPDATE sellers SET is_paid = TRUE, subscription_end = %s WHERE id = %s", (subscription_end, seller_id))
        c.execute("UPDATE subscription_requests SET status = 'approved' WHERE id = %s", (request_id,))
        conn.commit()
        flash('Subscription approved! Products are now permanently visible to buyers.', 'success')
    
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject_subscription/<int:request_id>')
@owner_required
def reject_subscription(request_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE subscription_requests SET status = 'rejected' WHERE id = %s", (request_id,))
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
    
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE bank_settings SET bank_name = %s, account_name = %s, account_number = %s, updated_at = CURRENT_TIMESTAMP", 
              (bank_name, account_name, account_number))
    conn.commit()
    conn.close()
    
    flash('Bank details updated!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/toggle_seller/<int:seller_id>')
@owner_required
def toggle_seller(seller_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE sellers SET is_active = NOT is_active WHERE id = %s", (seller_id,))
    conn.commit()
    conn.close()
    flash('Seller status updated', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_product/<int:product_id>')
@owner_required
def admin_delete_product(product_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = %s", (product_id,))
    conn.commit()
    conn.close()
    flash('Product deleted', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
