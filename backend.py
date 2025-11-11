import os
import sqlite3
import json
import time
from datetime import datetime
from uuid import uuid4
import traceback
from flask import Flask, render_template, request, jsonify, session, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import shutil

# =======================================================================
# 1. App Configuration & Setup
# =======================================================================

app = Flask(__name__)

# set secret key early so sessions work in routes
app.secret_key = os.environ.get("ICORE_SECRET", "dev-secret-please-change")

# Upload folder and allowed types
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_AVATAR_MIMETYPES = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'}
ALLOWED_AVATAR_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# DB path (same dir as this file)
DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')
# Ensure directory for DB exists
db_dir = os.path.dirname(DB_PATH)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)


def get_db_connection():
    """Return a sqlite3 connection with Row factory."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA foreign_keys = ON')
    except Exception:
        pass
    return conn


# =======================================================================
# 2. Database initialization & helpers
# =======================================================================

def _log(msg: str):
    """Append a debug message to registration.log with timestamp (UTC)."""
    try:
        p = os.path.join(os.path.dirname(__file__), 'registration.log')
        with open(p, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.utcnow().isoformat()}] {msg}\n")
    except Exception:
        pass


def ensure_schema():
    """
    Backward-compatible minimal schema initializer.
    This ensures the users/products/wishlists/carts tables exist and performs lightweight migrations.
    """
    init_db()  # delegate to the more complete initializer below


def execute_with_retry(fn, max_attempts=5, base_delay=0.05):
    """Run a DB write function with retries to handle SQLITE_BUSY transient locks."""
    attempt = 0
    while True:
        try:
            return fn()
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if 'database is locked' in msg or 'database table is locked' in msg or 'database disk image is malformed' in msg:
                attempt += 1
                if attempt >= max_attempts:
                    raise
                sleep = base_delay * (1.5 ** attempt)
                time.sleep(sleep)
                continue
            raise


def init_db():
    """
    Create tables if missing, perform idempotent migrations, and seed a demo user.
    Columns for users use 'password' to store hashed password (consistent across code).
    """
    conn = get_db_connection()
    c = conn.cursor()

    # Minimal users table (idempotent)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            password TEXT NOT NULL,
            avatar TEXT,
            wishlist TEXT,
            cart TEXT,
            listings TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    conn.commit()

    # Products table for persistent listings
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT,
            description TEXT,
            image TEXT,
            seller_email TEXT,
            seller_id INTEGER,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(seller_id) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')
    conn.commit()

    # Structured wishlist and cart tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS wishlists (
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            created_at TEXT,
            PRIMARY KEY(user_id, product_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS carts (
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT,
            PRIMARY KEY(user_id, product_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    ''')
    conn.commit()

    # Performance pragmas (best-effort)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    except Exception:
        pass

    # Ensure indices
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_wishlists_user ON wishlists(user_id)")
    conn.commit()

    # Normalize wishlist/cart/listings JSON defaults
    try:
        c.execute("UPDATE users SET wishlist = ? WHERE wishlist IS NULL", (json.dumps([]),))
        c.execute("UPDATE users SET cart = ? WHERE cart IS NULL", (json.dumps([]),))
        c.execute("UPDATE users SET listings = ? WHERE listings IS NULL", (json.dumps([]),))
        conn.commit()
    except Exception:
        conn.rollback()

    # Migrate legacy JSON fields into structured tables (idempotent)
    try:
        migrate_legacy_user_lists(conn)
    except Exception as e:
        _log(f"migrate_legacy_user_lists error: {e}")

    # Seed demo user if missing
    try:
        c.execute('SELECT 1 FROM users WHERE email = ?', ('sanskriti@example.com',))
        if not c.fetchone():
            now = datetime.utcnow().isoformat()
            c.execute(
                'INSERT INTO users (email, name, password, avatar, wishlist, cart, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    'sanskriti@example.com',
                    'Sanskriti',
                    generate_password_hash('password'),
                    'https://i.pravatar.cc/150?u=sanskriti',
                    json.dumps([2, 4]),
                    json.dumps([]),
                    now,
                    now,
                ))
            conn.commit()
    except Exception as e:
        _log(f"seed user failed: {e}")
        conn.rollback()

    conn.close()


def migrate_legacy_user_lists(conn):
    """
    Move legacy JSON wishlist/cart stored on users.wishlist/users.cart
    into structured wishlists and carts tables. Idempotent.
    """
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, wishlist, cart FROM users")
        rows = cur.fetchall()
    except Exception:
        return

    for user_row in rows:
        try:
            uid = user_row['id']
        except Exception:
            continue

        # wishlist
        try:
            wishlist_json = user_row['wishlist'] or '[]'
            items = json.loads(wishlist_json) if isinstance(wishlist_json, str) else wishlist_json
            if isinstance(items, list):
                for pid in items:
                    try:
                        cur.execute(
                            "INSERT OR IGNORE INTO wishlists(user_id, product_id, created_at) VALUES (?, ?, ?)",
                            (uid, int(pid), datetime.utcnow().isoformat())
                        )
                    except Exception:
                        pass
        except Exception:
            pass

        # cart
        try:
            cart_json = user_row['cart'] or '[]'
            cart_items = json.loads(cart_json) if isinstance(cart_json, str) else cart_json
            if isinstance(cart_items, list):
                for entry in cart_items:
                    try:
                        if isinstance(entry, dict):
                            pid = int(entry.get('product_id') or entry.get('id'))
                            qty = int(entry.get('quantity', 1))
                        else:
                            pid = int(entry)
                            qty = 1
                        cur.execute(
                            'INSERT OR IGNORE INTO carts (user_id, product_id, quantity, updated_at) VALUES (?, ?, ?, ?)',
                            (uid, pid, qty, datetime.utcnow().isoformat()))
                    except Exception:
                        pass
        except Exception:
            pass

    try:
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def ensure_db_ok(init_fn, db_path):
    """
    Try to run init_fn() to initialize the DB. If a sqlite DatabaseError occurs
    (corruption), try to move the corrupted file aside and re-run init_fn().
    Returns True on success, False on failure.
    """
    try:
        init_fn()
        return True
    except sqlite3.DatabaseError:
        ts = int(time.time())
        corrupt_name = f"{db_path}.corrupt.{ts}"
        try:
            # try moving the corrupted DB to a safe location
            shutil.move(db_path, corrupt_name)
        except Exception:
            # fallback: try copying then removing original
            try:
                shutil.copy2(db_path, corrupt_name)
                os.remove(db_path)
            except Exception:
                pass
        # attempt re-init
        try:
            init_fn()
            try:
                with open(os.path.join(os.path.dirname(__file__), 'registration.log'), 'a', encoding='utf-8') as fh:
                    fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Recovered corrupted DB -> {corrupt_name}\n")
            except Exception:
                pass
            return True
        except Exception:
            return False
    except Exception:
        return False


# -- Convenience helpers used across the app ---------------------------------

def row_to_dict(row):
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def get_user_by_email(email):
    """Return full user row (sqlite3.Row) or None."""
    if not email:
        return None
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
        r = cur.fetchone()
        return r
    finally:
        conn.close()


def get_user_id_by_email(email):
    """Return user id for an email or None."""
    row = get_user_by_email(email)
    return row['id'] if row else None


# =======================================================================
# 3. User creation / authentication (consistent with init_db schema)
# =======================================================================

def create_user(name: str, email: str, password: str):
    """
    Create a new user. If user with same email exists, return None.
    Stores hashed password in 'password' column to match init_db.
    """
    name = (name or "").strip()
    email = (email or "").strip().lower()
    if not (name and email and password):
        return None

    password_hash = generate_password_hash(password)

    def _fn():
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            now = datetime.utcnow().isoformat()
            cur.execute("""
                INSERT INTO users (name, email, password, avatar, wishlist, cart, listings, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                email,
                password_hash,
                None,
                json.dumps([]),
                json.dumps([]),
                json.dumps([]),
                now,
                now
            ))
            conn.commit()
            user_id = cur.lastrowid
            cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            return row_to_dict(cur.fetchone())
        finally:
            conn.close()

    try:
        return execute_with_retry(_fn)
    except sqlite3.IntegrityError:
        return None
    except Exception as e:
        _log(f"create_user error: {e}\n{traceback.format_exc()}")
        return None


def authenticate_user(email: str, password: str):
    """Return user dict (without password) if password matches, else None."""
    row = get_user_by_email(email)
    if not row:
        return None
    pw_hash = row.get('password') if 'password' in row.keys() else None
    if not pw_hash:
        return None
    if check_password_hash(pw_hash, password):
        user = row_to_dict(row)
        user.pop('password', None)
        return user
    return None


# =======================================================================
# 4. Product / wishlist / cart DB helpers (kept largely intact)
# =======================================================================

def get_all_products_from_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        'SELECT id, title, price, category, description, image, seller_email, created_at, updated_at FROM products ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    products = []
    for r in rows:
        products.append({
            'id': r['id'],
            'title': r['title'],
            'price': r['price'],
            'category': r['category'],
            'description': r['description'],
            'image': r['image'],
            'seller_email': r['seller_email'],
            'created_at': r['created_at'],
            'updated_at': r['updated_at']
        })
    return products


def save_user_wishlist(user_id, product_ids):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("DELETE FROM wishlists WHERE user_id = ?", (user_id,))
        for pid in product_ids:
            cur.execute(
                "INSERT OR REPLACE INTO wishlists(user_id, product_id, created_at) VALUES (?, ?, ?)",
                (user_id, int(pid), datetime.utcnow().isoformat())
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_user_cart(user_id, cart_items):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("DELETE FROM carts WHERE user_id = ?", (user_id,))
        for it in cart_items:
            pid = int(it.get("product_id") if isinstance(it, dict) else it)
            qty = int(it.get("quantity", 1) if isinstance(it, dict) else 1)
            cur.execute(
                "INSERT OR REPLACE INTO carts(user_id, product_id, quantity, updated_at) VALUES (?, ?, ?, ?)",
                (user_id, pid, qty, datetime.utcnow().isoformat())
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_product_in_db(title, price, category, description, image_path, seller_email, seller_id=None):
    conn = get_db_connection()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    try:
        cur.execute(
            "INSERT INTO products(title, price, category, description, image, seller_email, seller_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, float(price), category, description, image_path, seller_email, seller_id, now, now)
        )
        pid = cur.lastrowid
        conn.commit()
        cur.execute(
            "SELECT id, title, price, category, description, image, seller_email, created_at, updated_at FROM products WHERE id = ?",
            (pid,))
        row = cur.fetchone()
        if row:
            keys = ["id", "title", "price", "category", "description", "image", "seller_email", "created_at",
                    "updated_at"]
            prod = dict(zip(keys, row))
        else:
            prod = None
        return prod
    finally:
        conn.close()


def update_user_profile(user_id, name=None, avatar=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        fields = []
        params = []
        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if avatar is not None:
            fields.append("avatar = ?")
            params.append(avatar)
        if not fields:
            return
        params.append(datetime.utcnow().isoformat())
        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(fields)}, updated_at = ? WHERE id = ?"
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def get_user_wishlist_ids(user_id):
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT product_id FROM wishlists WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        return [r['product_id'] for r in cur.fetchall()]
    finally:
        conn.close()


def add_wishlist_item(user_id, product_id):
    def _fn():
        conn = get_db_connection()
        try:
            conn.execute("INSERT OR IGNORE INTO wishlists (user_id, product_id, created_at) VALUES (?, ?, ?)",
                         (user_id, int(product_id), datetime.utcnow().isoformat()))
            conn.commit()
        finally:
            conn.close()
    execute_with_retry(_fn)


def remove_wishlist_item(user_id, product_id):
    def _fn():
        conn = get_db_connection()
        try:
            conn.execute("DELETE FROM wishlists WHERE user_id = ? AND product_id = ?", (user_id, int(product_id)))
            conn.commit()
        finally:
            conn.close()
    execute_with_retry(_fn)


def get_cart_items(user_id):
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT product_id, quantity FROM carts WHERE user_id = ?", (user_id,))
        return {r['product_id']: r['quantity'] for r in cur.fetchall()}
    finally:
        conn.close()


def set_cart_item(user_id, product_id, quantity):
    def _fn():
        conn = get_db_connection()
        try:
            if int(quantity) <= 0:
                conn.execute("DELETE FROM carts WHERE user_id = ? AND product_id = ?", (user_id, int(product_id)))
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO carts (user_id, product_id, quantity, updated_at) VALUES (?, ?, ?, ?)",
                    (user_id, int(product_id), int(quantity), datetime.utcnow().isoformat()))
            conn.commit()
        finally:
            conn.close()
    execute_with_retry(_fn)


def update_user_lists(user_email, wishlist=None, cart=None, listings=None):
    if wishlist is None and cart is None and listings is None:
        return
    def _fn():
        conn = get_db_connection()
        try:
            if wishlist is not None:
                conn.execute("UPDATE users SET wishlist = ?, updated_at = ? WHERE email = ?",
                             (json.dumps(list(wishlist)), datetime.utcnow().isoformat(), user_email))
            if cart is not None:
                conn.execute("UPDATE users SET cart = ?, updated_at = ? WHERE email = ?",
                             (json.dumps(list(cart)), datetime.utcnow().isoformat(), user_email))
            if listings is not None:
                conn.execute("UPDATE users SET listings = ?, updated_at = ? WHERE email = ?",
                             (json.dumps(list(listings)), datetime.utcnow().isoformat(), user_email))
            conn.commit()
        finally:
            conn.close()
    execute_with_retry(_fn)


# =======================================================================
# 5. In-memory product list (used as fallback)
# =======================================================================

PRODUCTS = [
    {"id": 1, "title": 'Vintage Floral Dress', "price": 799, "category": 'Dresses',
     "image": 'https://images.unsplash.com/photo-1579369353590-7745c43a3b58?q=80&w=400',
     "description": 'Beautiful vintage dress from the 90s. Perfect condition, fits size M.',
     "seller_email": "system@example.com"},
    {"id": 2, "title": 'Classic Leather Jacket', "price": 1499, "category": 'Tops',
     "image": 'https://images.unsplash.com/photo-1551028719-00167b16eac5?q=80&w=400',
     "description": 'Timeless leather jacket. Barely worn. A staple for any wardrobe.',
     "seller_email": "system@example.com"},
    {"id": 3, "title": 'High-Waisted Jeans', "price": 450, "category": 'Tops',
     "image": 'https://images.unsplash.com/photo-1604176354204-926873782855?q=80&w=400',
     "description": 'Comfy and stylish high-waisted mom jeans. Size 28.', "seller_email": "system@example.com"},
    {"id": 4, "title": 'White Canvas Sneakers', "price": 699, "category": 'Shoes',
     "image": 'https://images.unsplash.com/photo-1595950653106-6c9ebd614d3a?q=80&w=400',
     "description": 'Goes with everything! Classic white sneakers in great condition. Size 7.',
     "seller_email": "system@example.com"},
    {"id": 5, "title": 'Summer Knit Top', "price": 299, "category": 'Tops',
     "image": 'https://images.unsplash.com/photo-1554424349-8eac3c38f172?q=80&w=400',
     "description": 'Light and airy knit top, perfect for summer evenings.', "seller_email": "system@example.com"},
    {"id": 6, "title": 'Pleated Pink Skirt', "price": 349, "category": 'Dresses',
     "image": 'https://images.unsplash.com/photo-1591047139829-d919b5ca23d2?q=80&w=400',
     "description": 'Fun and flirty pleated skirt. Excellent condition.', "seller_email": "system@example.com"},
]

# =======================================================================
# 6. Routes: frontend pages, auth, profile, products, uploads, health
# =======================================================================

@app.route('/')
def index():
    try:
        return render_template('login.html')
    except Exception:
        try:
            return send_from_directory(app.root_path, 'iCOREapp.html')
        except Exception:
            return "Login page not found", 404


@app.route('/app')
def app_page():
    try:
        return send_from_directory(app.root_path, 'iCOREapp.html')
    except Exception:
        return render_template('index.html')


@app.route('/register')
def register_page():
    try:
        return render_template('register.html')
    except Exception:
        return "Register page not found", 404


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    row = get_user_by_email(email)
    if row and check_password_hash(row['password'], password):
        session['user_email'] = email.strip().lower()
        return jsonify({"success": True, "message": "Login successful"})
    return jsonify({"success": False, "message": "Invalid email or password"}), 401


@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_email', None)
    return jsonify({"success": True, "message": "Logged out successfully"})


@app.route('/api/session_check')
def session_check():
    if 'user_email' in session:
        _log(f"session_check: logged in as {session['user_email']}")
        return jsonify({"isLoggedIn": True, "email": session['user_email']})
    _log('session_check: not logged in')
    return jsonify({"isLoggedIn": False})


@app.route('/api/user')
def get_user_data():
    if 'user_email' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    user_email = session['user_email']
    row = get_user_by_email(user_email)
    if row:
        wishlist = json.loads(row['wishlist'] or '[]')
        cart = json.loads(row['cart'] or '[]')
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            'SELECT id, title, price, category, description, image, seller_email, created_at, updated_at FROM products WHERE seller_email = ? ORDER BY id DESC',
            (user_email,))
        listings_rows = c.fetchall()
        conn.close()
        user_listings = []
        for r in listings_rows:
            user_listings.append({
                'id': r['id'],
                'title': r['title'],
                'price': r['price'],
                'category': r['category'],
                'description': r['description'],
                'image': r['image'],
                'seller_email': r['seller_email'],
                'created_at': r['created_at'],
                'updated_at': r['updated_at']
            })
        avatar = row['avatar'] if row['avatar'] else f"https://i.pravatar.cc/150?u={row['email']}"
        return jsonify({
            "name": row['name'],
            "email": row['email'],
            "avatar": avatar,
            "wishlist": wishlist,
            "cart": cart,
            "listings": user_listings
        })
    return jsonify({"error": "User not found"}), 404


@app.route('/api/products')
def get_products():
    try:
        products = get_all_products_from_db()
        return jsonify(products)
    except Exception:
        return jsonify(sorted(PRODUCTS, key=lambda p: p['id'], reverse=True))


@app.route('/api/user/avatar', methods=['POST'])
def upload_avatar():
    if 'user_email' not in session:
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    if 'avatar' not in request.files or request.files['avatar'].filename == '':
        return jsonify({"success": False, "message": "No file provided"}), 400

    file = request.files['avatar']
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_AVATAR_EXTS:
        return jsonify({"success": False, "message": "Unsupported file type"}), 400
    content_type = file.content_type or ''
    if content_type.split(';')[0] not in ALLOWED_AVATAR_MIMETYPES:
        return jsonify({"success": False, "message": "Unsupported file type"}), 400

    # Size check
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_AVATAR_SIZE:
        return jsonify({"success": False, "message": "File too large (max 5MB)"}), 400

    unique_name = f"{uuid4().hex}{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(filepath)
    avatar_url = '/' + filepath.replace('\\', '/')

    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('UPDATE users SET avatar = ?, updated_at = ? WHERE email = ?',
                  (avatar_url, datetime.utcnow().isoformat(), session['user_email']))
        conn.commit()
        conn.close()
        _log(f"avatar uploaded for {session['user_email']}: {avatar_url}")
        return jsonify({"success": True, "avatar": avatar_url})
    except Exception as e:
        _log(f"avatar upload failed for {session.get('user_email')}: {e}")
        return jsonify({"success": False, "message": "Failed to save avatar"}), 500


@app.route('/health')
def health():
    return jsonify({"status": "ok", "message": "server running"})


@app.route('/api/wishlist/toggle', methods=['POST'])
def toggle_wishlist():
    try:
        if 'user_email' not in session:
            return jsonify({"error": "Not authenticated"}), 401
        user_email = session['user_email']
        product_id = request.get_json().get('productId')
        row = get_user_by_email(user_email)
        if not row:
            return jsonify({"error": "User not found"}), 404
        uid = get_user_id_by_email(user_email)
        if uid is None:
            return jsonify({"error": "User not found"}), 404
        try:
            product_id = int(product_id)
        except Exception:
            return jsonify({"error": "Invalid product id"}), 400

        current = set(get_user_wishlist_ids(uid))
        if product_id in current:
            remove_wishlist_item(uid, product_id)
            action = 'removed'
        else:
            add_wishlist_item(uid, product_id)
            action = 'added'

        wishlist_ids = get_user_wishlist_ids(uid)
        update_user_lists(user_email, wishlist=wishlist_ids)
        return jsonify({"success": True, "action": action, "wishlist": wishlist_ids})
    except Exception as e:
        _log(f"toggle_wishlist exception: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Internal server error"}), 500


@app.route('/api/cart/update', methods=['POST'])
def update_cart():
    if 'user_email' not in session:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        user_email = session['user_email']
        data = request.get_json()
        product_id = data.get('productId')
        action = data.get('action', 'add')
        qty = int(data.get('quantity', 1))
        row = get_user_by_email(user_email)
        if not row:
            return jsonify({"error": "User not found"}), 404
        uid = get_user_id_by_email(user_email)
        if uid is None:
            return jsonify({"error": "User not found"}), 404
        try:
            product_id = int(product_id)
        except Exception:
            return jsonify({"error": "Invalid product id"}), 400

        cart_map = get_cart_items(uid)
        if action == 'add':
            new_qty = cart_map.get(product_id, 0) + qty
            set_cart_item(uid, product_id, new_qty)
        elif action == 'remove':
            set_cart_item(uid, product_id, 0)
        else:
            set_cart_item(uid, product_id, max(0, qty))

        current_cart = get_cart_items(uid)
        update_user_lists(user_email, cart=list(current_cart.keys()))
        return jsonify({"success": True, "cart": current_cart})
    except Exception as e:
        _log(f"update_cart exception: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Internal server error"}), 500


@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    if not (name and email and password):
        return jsonify({"success": False, "message": "Missing fields"}), 400
    user = create_user(name, email, password)
    if not user:
        _log(f"register attempt failed - user exists: {email}")
        return jsonify({"success": False, "message": "User already exists"}), 409
    session['user_email'] = email.strip().lower()
    _log(f"registered and auto-logged-in: {email}")
    try:
        wishlist = json.loads(user.get('wishlist') or '[]')
    except Exception:
        wishlist = []
    try:
        cart = json.loads(user.get('cart') or '[]')
    except Exception:
        cart = []
    avatar = user.get('avatar') if user.get('avatar') else f"https://i.pravatar.cc/150?u={user.get('email')}"
    return jsonify({
        "success": True,
        "message": "Account created",
        "user": {
            "id": user['id'],
            "email": user['email'],
            "name": user.get('name'),
            "avatar": avatar,
            "wishlist": wishlist,
            "cart": cart
        }
    }), 201


@app.route('/api/products/sell', methods=['POST'])
def sell_product():
    if 'user_email' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    if 'file-upload' not in request.files or request.files['file-upload'].filename == '':
        return jsonify({"error": "No image file provided"}), 400

    file = request.files['file-upload']
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid4().hex}{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(filepath)
    image_url = '/' + filepath.replace('\\', '/')

    title = request.form.get('title')
    try:
        price = float(request.form.get('price') or 0)
    except Exception:
        price = 0.0
    category = request.form.get('category')
    description = request.form.get('description')
    seller_email = session['user_email']

    try:
        created = create_product_in_db(title, price, category, description, image_url, seller_email)
        return jsonify({"success": True, "product": created}), 201
    except Exception as e:
        _log(f"sell_product failed: {e}")
        return jsonify({"success": False, "message": "Failed to save product"}), 500


@app.route('/debug/users')
def debug_list_users():
    if not app.debug:
        return jsonify({"error": "debug endpoint not available"}), 403
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, email, name, avatar, wishlist, cart, created_at, updated_at FROM users')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for r in rows:
        try:
            r['wishlist'] = json.loads(r.get('wishlist') or '[]')
        except Exception:
            r['wishlist'] = []
        try:
            r['cart'] = json.loads(r.get('cart') or '[]')
        except Exception:
            r['cart'] = []
        r['created_at'] = r.get('created_at') or None
        r['updated_at'] = r.get('updated_at') or None
    return jsonify(rows)


# =======================================================================
# 7. Startup: initialize DB and run server
# =======================================================================

# Initialize DB at module import/startup (runs once)
ok = ensure_db_ok(init_db, DB_PATH)
if not ok:
    print("Failed to initialize database. Check permissions or logs.")
    raise SystemExit(1)

if __name__ == '__main__':
    import os

    # Prefer platform PORT (Render, Heroku, etc.), then fall back to custom ICORE_PORT
    PORT = int(os.environ.get("PORT") or os.environ.get("ICORE_PORT", "5000"))
    HOST = os.environ.get("ICORE_HOST", "0.0.0.0")

    # Ensure Django settings module is set (adjust 'iCORE.settings' if your settings module is named differently)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iCORE.settings")

    try:
        from waitress import serve
        print(f"Starting app with Waitress on --> {HOST}:{PORT}")
        # If your app is a Flask app, serve(app, ...) is fine.
        # If `app` is a WSGI application (Django WSGI), ensure it's the WSGI callable (commonly named 'application').
        # If you use Django, change `serve(app, ...)` to `serve(application, ...)` where application = get_wsgi_application()
        serve(app, host=HOST, port=PORT)  # blocks
    except Exception as e:
        print(f"Waitress not available or failed ({e}), running fallback dev server on {HOST}:{PORT}")
        try:
            # If app is a Flask app:
            app.run(host=HOST, port=PORT, debug=False)
        except Exception:
            # If this is actually a Django WSGI app, try using the Django development server fallback
            from django.core.wsgi import get_wsgi_application
            application = get_wsgi_application()
            from waitress import serve as wait_serve  # attempt again
            wait_serve(application, host=HOST, port=PORT)

