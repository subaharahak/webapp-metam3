# app.py
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import mysql.connector
from mysql.connector import pooling
import threading
import time
import re
import json
import os
from datetime import datetime, timedelta
from p import check_card
from gen import CardGenerator

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Database connection pool
db_pool = pooling.MySQLConnectionPool(
    pool_name="webapp_pool",
    pool_size=5,
    pool_reset_session=True,
    host=os.environ.get('DB_HOST', 'sql12.freesqldatabase.com'),
    user=os.environ.get('DB_USER', 'sql12795630'),
    password=os.environ.get('DB_PASSWORD', 'fgqIine2LA'),
    database=os.environ.get('DB_NAME', 'sql12795630'),
    port=3306,
    autocommit=True
)

def connect_db():
    try:
        return db_pool.get_connection()
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

# Authentication and authorization functions (similar to your bot.py)
def is_admin(user_id):
    """Check if user is an admin"""
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        return False
        
    if user_id_int == 5103348494:  # MAIN_ADMIN_ID
        return True
        
    conn = connect_db()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM admins WHERE user_id = %s", (user_id_int,))
        result = cursor.fetchone()
        return result is not None
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False
    finally:
        if conn.is_connected():
            conn.close()

def is_premium(user_id):
    """Check if user has premium subscription"""
    if is_admin(user_id):
        return True
    
    conn = connect_db()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT subscription_expiry FROM premium_users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()

        if result:
            expiry = result['subscription_expiry']
            if expiry is None:
                return False
            else:
                if isinstance(expiry, str):
                    expiry = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
                return expiry > datetime.now()
        return False
    except Exception as e:
        print(f"Error checking premium status: {e}")
        return False
    finally:
        if conn.is_connected():
            conn.close()

def is_authorized(user_id):
    """Check if user is authorized"""
    if is_admin(user_id) or is_premium(user_id):
        return True
        
    conn = connect_db()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM free_users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        return result is not None
    except Exception as e:
        print(f"Error checking free user: {e}")
        return False
    finally:
        if conn.is_connected():
            conn.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not is_admin(session['user_id']):
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'user_id' in session and is_authorized(session['user_id']):
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # In a real app, you'd have a proper registration form
        # For now, we'll auto-register if the user is not already registered
        if 'user_id' not in session:
            return redirect(url_for('index'))
            
        user_id = session['user_id']
        first_name = session.get('first_name', 'User')
        
        conn = connect_db()
        if not conn:
            return render_template('register.html', error="Database connection failed")
            
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT IGNORE INTO free_users (user_id, first_name) VALUES (%s, %s)", 
                          (user_id, first_name))
            conn.commit()
            
            return redirect(url_for('dashboard'))
        except Exception as e:
            print(f"Error registering user: {e}")
            return render_template('register.html', error="Registration failed")
        finally:
            if conn.is_connected():
                conn.close()
    
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    if not is_authorized(user_id):
        return redirect(url_for('register'))
    
    # Get user info
    user_info = {
        'user_id': user_id,
        'first_name': session.get('first_name', 'User'),
        'is_admin': is_admin(user_id),
        'is_premium': is_premium(user_id)
    }
    
    return render_template('dashboard.html', user=user_info)

@app.route('/check_single', methods=['GET', 'POST'])
@login_required
def check_single():
    if not is_authorized(session['user_id']):
        return redirect(url_for('register'))
    
    if request.method == 'POST':
        cc_data = request.form.get('cc_data')
        if not cc_data:
            return render_template('check_single.html', error="Please provide card data")
        
        # Normalize the card data (using your existing function)
        normalized_cc = normalize_card(cc_data)
        if not normalized_cc:
            return render_template('check_single.html', error="Invalid card format")
        
        # Check the card (this will run in a background thread)
        result = check_card(normalized_cc)
        
        # If approved, send to Telegram (you'll need to implement this)
        if "APPROVED CC ✅" in result:
            send_to_telegram(result, session['user_id'])
        
        return render_template('check_single.html', result=result, cc_data=cc_data)
    
    return render_template('check_single.html')

@app.route('/check_mass', methods=['GET', 'POST'])
@login_required
def check_mass():
    if not is_authorized(session['user_id']):
        return redirect(url_for('register'))
    
    # Check if user is premium or admin for mass checking
    user_id = session['user_id']
    if not is_admin(user_id) and not is_premium(user_id):
        return render_template('dashboard.html', error="Mass check is only available for premium users")
    
    if request.method == 'POST':
        if 'cc_file' not in request.files:
            return render_template('check_mass.html', error="No file uploaded")
        
        file = request.files['cc_file']
        if file.filename == '':
            return render_template('check_mass.html', error="No file selected")
        
        if file and file.filename.endswith('.txt'):
            text = file.read().decode('utf-8', errors='ignore')
            
            # Extract CCs using your existing logic
            cc_lines = []
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                
                normalized_cc = normalize_card(line)
                if normalized_cc:
                    cc_lines.append(normalized_cc)
                else:
                    found = re.findall(r'\b(?:\d[ -]*?){13,16}\b.*?\|.*?\|.*?\|.*', line)
                    if found:
                        cc_lines.extend(found)
                    else:
                        parts = re.findall(r'\d{12,16}[|: -]\d{1,2}[|: -]\d{2,4}[|: -]\d{3,4}', line)
                        cc_lines.extend(parts)
            
            if not cc_lines:
                return render_template('check_mass.html', error="No valid cards found in the file")
            
            # Process cards in background
            threading.Thread(target=process_mass_check, args=(cc_lines, user_id)).start()
            
            return render_template('check_mass.html', 
                                 message=f"Started processing {len(cc_lines)} cards. Results will be sent to your Telegram.")
        
        return render_template('check_mass.html', error="Invalid file format. Please upload a .txt file")
    
    return render_template('check_mass.html')

@app.route('/generate', methods=['GET', 'POST'])
@login_required
def generate_cards():
    if not is_authorized(session['user_id']):
        return redirect(url_for('register'))
    
    if request.method == 'POST':
        pattern = request.form.get('pattern')
        if not pattern:
            return render_template('generate.html', error="Please provide a pattern")
        
        card_generator = CardGenerator()
        cards, error = card_generator.generate_cards(pattern, 10)
        
        if error:
            return render_template('generate.html', error=error)
        
        return render_template('generate.html', cards=cards, pattern=pattern)
    
    return render_template('generate.html')

@app.route('/redeem', methods=['GET', 'POST'])
@login_required
def redeem_key():
    if request.method == 'POST':
        key = request.form.get('key')
        if not key:
            return render_template('redeem.html', error="Please enter a key")
        
        user_id = session['user_id']
        
        # Check if key is valid
        conn = connect_db()
        if not conn:
            return render_template('redeem.html', error="Database connection failed")
        
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM premium_keys WHERE `key` = %s AND used_by IS NULL", (key,))
            key_data = cursor.fetchone()
            
            if not key_data:
                return render_template('redeem.html', error="Invalid or already used key")
            
            # Mark key as used and add premium
            validity_days = key_data['validity_days']
            expiry_date = datetime.now() + timedelta(days=validity_days)
            
            cursor.execute(
                "UPDATE premium_keys SET used_by = %s, used_at = NOW() WHERE `key` = %s",
                (user_id, key)
            )
            
            cursor.execute("""
                INSERT INTO premium_users (user_id, first_name, subscription_expiry)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    first_name = VALUES(first_name),
                    subscription_start = CURRENT_TIMESTAMP,
                    subscription_expiry = VALUES(subscription_expiry)
            """, (user_id, session.get('first_name', 'User'), expiry_date))
            
            conn.commit()
            
            return render_template('redeem.html', 
                                 success=f"Key redeemed successfully! Premium active for {validity_days} days.")
        
        except Exception as e:
            print(f"Error redeeming key: {e}")
            return render_template('redeem.html', error="Error redeeming key")
        finally:
            if conn.is_connected():
                conn.close()
    
    return render_template('redeem.html')

@app.route('/admin')
@admin_required
def admin_panel():
    # Get admin stats
    conn = connect_db()
    if not conn:
        return render_template('admin.html', error="Database connection failed")
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Get user counts
        cursor.execute("SELECT COUNT(*) as count FROM free_users")
        free_users = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM premium_users WHERE subscription_expiry > NOW()")
        premium_users = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM admins")
        admins_count = cursor.fetchone()['count']
        
        # Get recent activity
        cursor.execute("""
            SELECT user_id, first_name, subscription_expiry 
            FROM premium_users 
            ORDER BY subscription_start DESC 
            LIMIT 10
        """)
        recent_premium = cursor.fetchall()
        
        return render_template('admin.html', 
                             free_users=free_users,
                             premium_users=premium_users,
                             admins_count=admins_count,
                             recent_premium=recent_premium)
    
    except Exception as e:
        print(f"Error loading admin data: {e}")
        return render_template('admin.html', error="Error loading admin data")
    finally:
        if conn.is_connected():
            conn.close()

@app.route('/subscription')
@login_required
def subscription():
    user_id = session['user_id']
    
    if is_admin(user_id):
        status = "Admin 👑"
        expiry = "Never"
    elif is_premium(user_id):
        conn = connect_db()
        if conn:
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT subscription_expiry FROM premium_users WHERE user_id = %s", (user_id,))
                result = cursor.fetchone()
                if result:
                    expiry_date = result['subscription_expiry']
                    if isinstance(expiry_date, str):
                        expiry_date = datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S")
                    remaining_days = (expiry_date - datetime.now()).days
                    status = f"Premium ({remaining_days} days remaining)"
                    expiry = expiry_date.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    status = "Free User"
                    expiry = "N/A"
            except Exception as e:
                print(f"Error getting subscription info: {e}")
                status = "Free User"
                expiry = "N/A"
            finally:
                if conn.is_connected():
                    conn.close()
        else:
            status = "Free User"
            expiry = "N/A"
    else:
        status = "Free User"
        expiry = "N/A"
    
    return render_template('subscription.html', status=status, expiry=expiry)

@app.route('/login', methods=['POST'])
def login():
    # This is a simplified login - in a real app, you'd have proper authentication
    # For now, we'll just set the user ID from the form
    user_id = request.form.get('user_id')
    first_name = request.form.get('first_name', 'User')
    
    if user_id:
        session['user_id'] = user_id
        session['first_name'] = first_name
        return redirect(url_for('dashboard'))
    
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# Helper functions
def normalize_card(text):
    """Normalize credit card from any format to cc|mm|yy|cvv"""
    if not text:
        return None

    text = text.replace('\n', ' ').replace('/', ' ')
    numbers = re.findall(r'\d+', text)

    cc = mm = yy = cvv = ''

    for part in numbers:
        if len(part) == 16:
            cc = part
        elif len(part) == 4 and part.startswith('20'):
            yy = part
        elif len(part) == 2 and int(part) <= 12 and mm == '':
            mm = part
        elif len(part) == 2 and not part.startswith('20') and yy == '':
            yy = '20' + part
        elif len(part) in [3, 4] and cvv == '':
            cvv = part

    if cc and mm and yy and cvv:
        return f"{cc}|{mm}|{yy}|{cvv}"

    return None

def process_mass_check(cc_lines, user_id):
    """Process mass check in background"""
    approved_cards = []
    
    for cc in cc_lines:
        try:
            result = check_card(cc.strip())
            if "APPROVED CC ✅" in result:
                approved_cards.append(result)
                # Send to Telegram
                send_to_telegram(result, user_id)
        except Exception as e:
            print(f"Error checking card {cc}: {e}")
    
    # Send summary to Telegram
    if approved_cards:
        summary = f"Mass check completed. Found {len(approved_cards)} approved cards out of {len(cc_lines)}."
        send_to_telegram(summary, user_id)

def send_to_telegram(message, user_id):
    """Send message to Telegram bot"""
    # You'll need to implement this using your Telegram bot
    # This is just a placeholder
    print(f"Would send to Telegram (user {user_id}): {message}")
    # Actual implementation would use the Telegram Bot API

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

# Add this to your existing app.py

# Health check endpoint for Render
@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

# Only run this if executed directly (not through gunicorn)
if __name__ == '__main__':
    # Check if we're running in production (on Render)
    if os.environ.get('RENDER', None):
        # Production settings
        app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))
    else:
        # Development settings
        from dotenv import load_dotenv
        load_dotenv()  # Load environment variables from .env file
        app.run(debug=True, host='0.0.0.0', port=5000)