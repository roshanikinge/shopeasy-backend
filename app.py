from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_mail import Mail, Message
import mysql.connector
import json
from datetime import datetime, timedelta
import secrets
import threading
from config import DB_CONFIG

# from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)

CORS(app, origins=["https://shopeasy-frontend.vercel.app", "http://localhost:3000"])

# ========== EMAIL CONFIGURATION ==========
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'roshanikinge17@gmail.com'
app.config['MAIL_PASSWORD'] = 'yqqeifvferapwfms'
app.config['MAIL_DEFAULT_SENDER'] = 'roshanikinge17@gmail.com'

mail = Mail(app)

CORS(app, origins="*", allow_headers=["Content-Type"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# SocketIO (reduced logging)
# socketio = SocketIO(
#     app,
#     cors_allowed_origins="*",
#     logger=False,
#     engineio_logger=False,
#     ping_interval=25,
#     ping_timeout=60
# )

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
    return response

# ========== ASYNC EMAIL HELPER ==========
def send_email_async(to_email, subject, body):
    def _send():
        try:
            msg = Message(subject, recipients=[to_email])
            msg.body = body
            mail.send(msg)
            print(f"✅ Email sent to {to_email}")
        except Exception as e:
            print(f"❌ Email failed to {to_email}: {e}")
    thread = threading.Thread(target=_send)
    thread.daemon = True
    thread.start()

# ========== HELPER FUNCTIONS ==========
def create_notification(user_id, notif_type, title, message, link=None):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO notifications (user_id, type, title, message, link) VALUES (%s, %s, %s, %s, %s)",
        (user_id, notif_type, title, message, link)
    )
    db.commit()
    cursor.close()
    db.close()

def get_admin_user_ids():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE role = 'admin'")
    admins = cursor.fetchall()
    cursor.close()
    db.close()
    return [a[0] for a in admins]

def generate_reset_token(email):
    return secrets.token_urlsafe(32)

# ========== FORGOT PASSWORD ==========
@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.json
    email = data.get('email')
    if not email:
        return jsonify({"error": "Email required"}), 400
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "If that email exists, a reset link has been sent."}), 200
    
    token = generate_reset_token(email)
    expires_at = datetime.now() + timedelta(hours=1)
    
    cursor2 = db.cursor()
    cursor2.execute(
        "INSERT INTO password_resets (user_id, token, expires_at) VALUES (%s, %s, %s)",
        (user['id'], token, expires_at)
    )
    db.commit()
    cursor2.close()
    
    reset_link = f"http://localhost:3000/reset-password/{token}"
    send_email_async(
        email,
        "Reset Your Password – ShopEasy",
        f"Hello {user['name']},\n\nClick the link below to reset your password (valid for 1 hour):\n{reset_link}\n\nIf you didn't request this, please ignore this email.\n\nShopEasy Team"
    )
    cursor.close()
    db.close()
    return jsonify({"message": "If that email exists, a reset link has been sent."}), 200

@app.route('/reset-password/<token>', methods=['POST'])
def reset_password(token):
    data = request.json
    new_password = data.get('password')
    if not new_password or len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT user_id, expires_at FROM password_resets WHERE token = %s AND expires_at > NOW()",
        (token,)
    )
    reset = cursor.fetchone()
    if not reset:
        return jsonify({"error": "Invalid or expired reset token"}), 400
    
    user_id = reset['user_id']
    cursor2 = db.cursor()
    cursor2.execute("UPDATE users SET password = %s WHERE id = %s", (new_password, user_id))
    db.commit()
    cursor2.close()
    
    cursor3 = db.cursor()
    cursor3.execute("DELETE FROM password_resets WHERE token = %s", (token,))
    db.commit()
    cursor3.close()
    
    cursor.close()
    db.close()
    return jsonify({"message": "Password reset successfully. You can now login."}), 200

# ========== MAIN ROUTES ==========
@app.route('/')
def home():
    return {"message": "Ecommerce API is running! 🎉"}

# ─── REGISTER ───
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    name = data['name']
    email = data['email']
    password = data['password']
    role = data.get('role', 'user')
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
            (name, email, password, role)
        )
        db.commit()
        send_email_async(
            email,
            "Welcome to ShopEasy!",
            f"Hello {name},\n\nYour account has been created successfully.\n\nYou can now login and start shopping.\n\nThank you,\nShopEasy Team"
        )
        return jsonify({"message": "User registered successfully!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        cursor.close()
        db.close()

# ─── LOGIN ───
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data['email']
    password = data['password']
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM users WHERE email=%s AND password=%s",
        (email, password)
    )
    user = cursor.fetchone()
    cursor.close()
    db.close()
    if user:
        send_email_async(
            user['email'],
            "Login Alert – ShopEasy",
            f"Hello {user['name']},\n\nYou have successfully logged into your ShopEasy account.\n\nIf this wasn't you, please contact support immediately.\n\nThank you,\nShopEasy Team"
        )
        return jsonify({
            "message": "Login successful!",
            "user": {
                "id": user['id'],
                "name": user['name'],
                "email": user['email'],
                "role": user['role']
            }
        }), 200
    else:
        return jsonify({"error": "Invalid email or password"}), 401

# ─── GET ALL PRODUCTS WITH SEARCH, CATEGORY & PRICE FILTER ───
@app.route('/products', methods=['GET'])
def get_products():
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    min_price = request.args.get('min_price', 0, type=float)
    max_price = request.args.get('max_price', 100000, type=float)
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    query = "SELECT * FROM products WHERE 1=1"
    params = []
    
    if search:
        query += " AND (name LIKE %s OR description LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])
    
    if category and category != 'All':
        query += " AND category = %s"
        params.append(category)
    
    if min_price > 0:
        query += " AND price >= %s"
        params.append(min_price)
    
    if max_price < 100000:
        query += " AND price <= %s"
        params.append(max_price)
    
    cursor.execute(query, params)
    products = cursor.fetchall()
    
    for p in products:
        if p.get('images'):
            p['images'] = json.loads(p['images'])
        else:
            p['images'] = []
    
    cursor.close()
    db.close()
    return jsonify(products), 200

# ─── ADD PRODUCT ───
@app.route('/products/add', methods=['POST', 'OPTIONS'])
def add_product():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    name = data['name']
    description = data['description']
    price = data['price']
    stock = data.get('stock', 0)
    category = data.get('category', 'Electronics')
    discount = data.get('discount', 0)
    rating = data.get('rating', 0)
    images = data.get('images', [])
    return_days = data.get('return_days', 10)
    images_json = json.dumps(images) if images else None

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """INSERT INTO products
           (name, description, price, stock, category, discount, rating, images, return_days)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (name, description, price, stock, category, discount, rating, images_json, return_days)
    )
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Product added successfully!"}), 201

# ─── DELETE PRODUCT ───
@app.route('/products/delete/<int:id>', methods=['DELETE', 'OPTIONS'])
def delete_product(id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM cart WHERE product_id = %s", (id,))
    cursor.execute("DELETE FROM products WHERE id = %s", (id,))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Product deleted successfully!"}), 200

# ─── CART ROUTES ──────────────────────────────────────────
@app.route('/cart/check/<int:user_id>/<int:product_id>', methods=['GET'])
def check_in_cart(user_id, product_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, quantity FROM cart WHERE user_id=%s AND product_id=%s", (user_id, product_id))
    item = cursor.fetchone()
    cursor.close()
    db.close()
    return jsonify({"in_cart": item is not None, "quantity": item['quantity'] if item else 0})

@app.route('/cart/add', methods=['POST', 'OPTIONS'])
def add_to_cart():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    user_id = data['user_id']
    product_id = data['product_id']
    quantity = data.get('quantity', 1)
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (%s, %s, %s)", (user_id, product_id, quantity))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Product added to cart!"}), 201

@app.route('/cart/<int:user_id>', methods=['GET'])
def get_cart(user_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT cart.id, products.id AS product_id, products.name, products.description, products.price,
               products.images, cart.quantity
        FROM cart
        JOIN products ON cart.product_id = products.id
        WHERE cart.user_id = %s
    """, (user_id,))
    items = cursor.fetchall()
    for item in items:
        if item.get('images'):
            img_list = json.loads(item['images'])
            item['image_url'] = img_list[0] if img_list else ''
        else:
            item['image_url'] = ''
    cursor.close()
    db.close()
    return jsonify(items), 200

@app.route('/cart/remove/<int:id>', methods=['DELETE', 'OPTIONS'])
def remove_from_cart(id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM cart WHERE id=%s", (id,))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Product removed from cart!"}), 200

@app.route('/cart/update/<int:cart_id>', methods=['PUT', 'OPTIONS'])
def update_cart_quantity(cart_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    quantity = data.get('quantity', 1)
    if quantity < 1:
        return jsonify({"error": "Quantity must be at least 1"}), 400
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE cart SET quantity = %s WHERE id = %s", (quantity, cart_id))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Cart updated successfully!"}), 200

@app.route('/cart/check-batch', methods=['POST'])
def check_cart_batch():
    data = request.json
    user_id = data['user_id']
    product_ids = data['product_ids']
    if not product_ids:
        return jsonify({}), 200
    db = get_db()
    cursor = db.cursor(dictionary=True)
    placeholders = ','.join(['%s'] * len(product_ids))
    cursor.execute(f"""
        SELECT product_id, quantity FROM cart 
        WHERE user_id = %s AND product_id IN ({placeholders})
    """, [user_id] + product_ids)
    results = cursor.fetchall()
    cursor.close()
    db.close()
    status = {row['product_id']: True for row in results}
    return jsonify(status), 200

# ─── WISHLIST ROUTES ──────────────────────────────────────────
@app.route('/wishlist/add', methods=['POST', 'OPTIONS'])
def add_to_wishlist():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    user_id = data['user_id']
    product_id = data['product_id']
    
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO wishlist (user_id, product_id) VALUES (%s, %s)",
            (user_id, product_id)
        )
        db.commit()
        return jsonify({"message": "Product added to wishlist!"}), 201
    except mysql.connector.IntegrityError:
        return jsonify({"message": "Product already in wishlist"}), 200
    finally:
        cursor.close()
        db.close()

@app.route('/wishlist/remove/<int:product_id>', methods=['DELETE', 'OPTIONS'])
def remove_from_wishlist(product_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    user_id = request.args.get('user_id') or request.json.get('user_id')
    if not user_id:
        return jsonify({"error": "User ID required"}), 400
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM wishlist WHERE user_id = %s AND product_id = %s",
        (user_id, product_id)
    )
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Product removed from wishlist"}), 200

@app.route('/wishlist/<int:user_id>', methods=['GET'])
def get_wishlist(user_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.id, p.name, p.description, p.price, p.images, p.discount, p.stock, p.rating
        FROM wishlist w
        JOIN products p ON w.product_id = p.id
        WHERE w.user_id = %s
        ORDER BY w.created_at DESC
    """, (user_id,))
    items = cursor.fetchall()
    for item in items:
        if item.get('images'):
            item['images'] = json.loads(item['images'])
            item['image_url'] = item['images'][0] if item['images'] else ''
        else:
            item['image_url'] = ''
    cursor.close()
    db.close()
    return jsonify(items), 200

@app.route('/wishlist/check/<int:user_id>/<int:product_id>', methods=['GET'])
def check_in_wishlist(user_id, product_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT id FROM wishlist WHERE user_id = %s AND product_id = %s",
        (user_id, product_id)
    )
    exists = cursor.fetchone()
    cursor.close()
    db.close()
    return jsonify({"in_wishlist": exists is not None}), 200

@app.route('/wishlist/check-batch', methods=['POST'])
def check_wishlist_batch():
    data = request.json
    user_id = data['user_id']
    product_ids = data['product_ids']
    if not product_ids:
        return jsonify({}), 200
    db = get_db()
    cursor = db.cursor(dictionary=True)
    placeholders = ','.join(['%s'] * len(product_ids))
    cursor.execute(f"""
        SELECT product_id FROM wishlist 
        WHERE user_id = %s AND product_id IN ({placeholders})
    """, [user_id] + product_ids)
    results = cursor.fetchall()
    cursor.close()
    db.close()
    status = {row['product_id']: True for row in results}
    return jsonify(status), 200

# ─── PLACE ORDER ──────────────────────────────────────────
@app.route('/order/place', methods=['POST', 'OPTIONS'])
def place_order():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    user_id = data['user_id']
    payment_method = data.get('payment_method', 'cod')
    
    shipping_name = data.get('shipping_name')
    shipping_phone = data.get('shipping_phone')
    shipping_address = data.get('shipping_address')
    shipping_city = data.get('shipping_city')
    shipping_pincode = data.get('shipping_pincode')
    shipping_state = data.get('shipping_state')
    delivery_instructions = data.get('delivery_instructions', '')
    delivery_latitude = data.get('delivery_latitude')
    delivery_longitude = data.get('delivery_longitude')
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT cart.id, cart.product_id, cart.quantity,
               products.price
        FROM cart
        JOIN products ON cart.product_id = products.id
        WHERE cart.user_id = %s
    """, (user_id,))
    cart_items = cursor.fetchall()
    if not cart_items:
        return jsonify({"error": "Cart is empty!"}), 400
        
    total = sum(float(item['price']) * item['quantity'] for item in cart_items)
    estimated_delivery = datetime.now() + timedelta(days=3)
    
    cursor2 = db.cursor()
    cursor2.execute("""
        INSERT INTO orders (user_id, total_amount, status, estimated_delivery, payment_method,
        shipping_name, shipping_phone, shipping_address, shipping_city, shipping_pincode, shipping_state, delivery_instructions,
        delivery_latitude, delivery_longitude)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (user_id, total, 'confirmed', estimated_delivery, payment_method,
          shipping_name, shipping_phone, shipping_address, shipping_city, shipping_pincode, shipping_state, delivery_instructions,
          delivery_latitude, delivery_longitude))
    db.commit()
    order_id = cursor2.lastrowid
    
    for item in cart_items:
        cursor2.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
            (order_id, item['product_id'], item['quantity'], item['price'])
        )
    
    cursor2.execute("DELETE FROM cart WHERE user_id=%s", (user_id,))
    db.commit()
    
    user_email = None
    user_name = None
    cursor3 = db.cursor(dictionary=True)
    cursor3.execute("SELECT email, name FROM users WHERE id = %s", (user_id,))
    user_data = cursor3.fetchone()
    if user_data:
        user_email = user_data['email']
        user_name = user_data['name']
    cursor3.close()
    
    if user_email:
        send_email_async(
            user_email,
            "Order Confirmed – ShopEasy",
            f"Hello {user_name},\n\nYour order #{order_id} has been placed successfully!\nTotal amount: ₹{total}\nEstimated delivery: {estimated_delivery.strftime('%Y-%m-%d')}\n\nThank you for shopping with us.\n\nShopEasy Team"
        )
    
    cursor.close()
    cursor2.close()
    db.close()
    
    return jsonify({
        "message": "Order placed successfully! ✅",
        "order_id": order_id,
        "estimated_delivery": str(estimated_delivery),
        "payment_method": payment_method
    }), 201

# ─── GET ORDER HISTORY ─────────────────────────────────────
@app.route('/orders/<int:user_id>', methods=['GET'])
def get_orders(user_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT orders.id, orders.total_amount,
               orders.status, orders.created_at,
               orders.estimated_delivery, orders.payment_method,
               orders.shipping_name, orders.shipping_phone, orders.shipping_address,
               orders.shipping_city, orders.shipping_pincode, orders.shipping_state,
               orders.delivery_instructions
        FROM orders
        WHERE orders.user_id = %s
        ORDER BY orders.created_at DESC
    """, (user_id,))
    orders = cursor.fetchall()
    for order in orders:
        cursor.execute("""
            SELECT products.id AS product_id, products.name, products.description, products.images,
                   order_items.quantity, order_items.price
            FROM order_items
            JOIN products ON order_items.product_id = products.id
            WHERE order_items.order_id = %s
        """, (order['id'],))
        items = cursor.fetchall()
        for it in items:
            if it.get('images'):
                img_list = json.loads(it['images'])
                it['image_url'] = img_list[0] if img_list else ''
            else:
                it['image_url'] = ''
        order['items'] = items
        order['created_at'] = str(order['created_at'])
        order['estimated_delivery'] = str(order['estimated_delivery']) if order['estimated_delivery'] else None
    cursor.close()
    db.close()
    return jsonify(orders), 200

# ─── CANCEL ORDER ─────────────────────────────────────────
@app.route('/order/cancel/<int:order_id>', methods=['PUT', 'OPTIONS'])
def cancel_order(order_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT status, user_id FROM orders WHERE id=%s", (order_id,))
    order = cursor.fetchone()
    if not order:
        return jsonify({"error": "Order not found!"}), 404
    if order['status'] == 'delivered':
        return jsonify({"error": "Delivered orders cannot be cancelled!"}), 400
    if order['status'] == 'cancelled':
        return jsonify({"error": "Order already cancelled!"}), 400
    cursor2 = db.cursor()
    cursor2.execute("UPDATE orders SET status='cancelled' WHERE id=%s", (order_id,))
    db.commit()
    cursor.close()
    cursor2.close()
    user_id = order['user_id']
    cursor3 = db.cursor(dictionary=True)
    cursor3.execute("SELECT email, name FROM users WHERE id = %s", (user_id,))
    user_data = cursor3.fetchone()
    cursor3.close()
    if user_data:
        send_email_async(
            user_data['email'],
            "Order Cancelled – ShopEasy",
            f"Hello {user_data['name']},\n\nYour order #{order_id} has been cancelled.\n\nIf this was a mistake, please contact support.\n\nShopEasy Team"
        )
    db.close()
    return jsonify({"message": "Order cancelled successfully!"}), 200

# ─── DELETE CANCELLED ORDER ───────────────────────────────
@app.route('/order/delete/<int:order_id>', methods=['DELETE', 'OPTIONS'])
def delete_order(order_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT status FROM orders WHERE id=%s", (order_id,))
    order = cursor.fetchone()
    if not order:
        return jsonify({"error": "Order not found!"}), 404
    if order['status'] != 'cancelled':
        return jsonify({"error": "Only cancelled orders can be deleted!"}), 400
    cursor2 = db.cursor()
    cursor2.execute("DELETE FROM order_items WHERE order_id=%s", (order_id,))
    cursor2.execute("DELETE FROM orders WHERE id=%s", (order_id,))
    db.commit()
    cursor.close()
    cursor2.close()
    db.close()
    return jsonify({"message": "Order removed successfully!"}), 200

# ─── REORDER ──────────────────────────────────────────────
@app.route('/order/reorder/<int:order_id>', methods=['POST', 'OPTIONS'])
def reorder(order_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    user_id = data['user_id']
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT product_id, quantity, price FROM order_items WHERE order_id=%s", (order_id,))
    items = cursor.fetchall()
    if not items:
        return jsonify({"error": "Order items not found!"}), 404
    total = sum(float(item['price']) * item['quantity'] for item in items)
    cursor2 = db.cursor()
    cursor2.execute("INSERT INTO orders (user_id, total_amount, status) VALUES (%s, %s, %s)", (user_id, total, 'confirmed'))
    db.commit()
    new_order_id = cursor2.lastrowid
    for item in items:
        cursor2.execute("INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
                        (new_order_id, item['product_id'], item['quantity'], item['price']))
    db.commit()
    cursor.close()
    cursor2.close()
    db.close()
    return jsonify({"message": "Order placed again successfully! ✅", "order_id": new_order_id}), 201

# ─── TRACK ORDER ──────────────────────────────────────────
@app.route('/order/track/<int:order_id>', methods=['GET'])
def track_order(order_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT orders.id, orders.status,
               orders.created_at, orders.total_amount,
               users.name as customer_name
        FROM orders
        JOIN users ON orders.user_id = users.id
        WHERE orders.id = %s
    """, (order_id,))
    order = cursor.fetchone()
    if not order:
        return jsonify({"error": "Order not found!"}), 404
    order['created_at'] = str(order['created_at'])
    cursor.close()
    db.close()
    return jsonify(order), 200

# ─── ADMIN ROUTES ──────────────────────────────────────────
@app.route('/admin/orders', methods=['GET'])
def get_all_orders():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT orders.id, orders.total_amount,
               orders.status, orders.created_at,
               users.name as customer_name,
               users.email as customer_email,
               users.phone as customer_phone,
               users.address as customer_address,
               users.city as customer_city,
               users.pincode as customer_pincode,
               users.state as customer_state,
               orders.shipping_name, orders.shipping_phone, orders.shipping_address,
               orders.shipping_city, orders.shipping_pincode, orders.shipping_state,
               orders.delivery_instructions,
               orders.delivery_latitude, orders.delivery_longitude
        FROM orders
        JOIN users ON orders.user_id = users.id
        ORDER BY orders.created_at DESC
    """)
    orders = cursor.fetchall()
    for order in orders:
        cursor.execute("""
            SELECT products.name, order_items.quantity,
                   order_items.price, products.images
            FROM order_items
            JOIN products ON order_items.product_id = products.id
            WHERE order_items.order_id = %s
        """, (order['id'],))
        items = cursor.fetchall()
        for it in items:
            if it.get('images'):
                img_list = json.loads(it['images'])
                it['image_url'] = img_list[0] if img_list else ''
            else:
                it['image_url'] = ''
        order['items'] = items
        order['created_at'] = str(order['created_at'])
    cursor.close()
    db.close()
    return jsonify(orders), 200

@app.route('/admin/order/status/<int:order_id>', methods=['PUT', 'OPTIONS'])
def update_order_status(order_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    status = data['status']
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE orders SET status=%s WHERE id=%s", (status, order_id))
    db.commit()
    
    cursor2 = db.cursor(dictionary=True)
    cursor2.execute("SELECT user_id FROM orders WHERE id = %s", (order_id,))
    order = cursor2.fetchone()
    if order:
        user_id = order['user_id']
        status_text = {'confirmed':'Confirmed', 'out_for_delivery':'Out for Delivery', 'delivered':'Delivered', 'cancelled':'Cancelled'}.get(status, status)
        create_notification(
            user_id,
            'order_status',
            f'Order #{order_id} {status_text}',
            f'Your order status has been updated to {status_text}.',
            '/orders'
        )
        if status == 'delivered':
            cursor3 = db.cursor(dictionary=True)
            cursor3.execute("SELECT email, name FROM users WHERE id = %s", (user_id,))
            user_data = cursor3.fetchone()
            cursor3.close()
            if user_data:
                send_email_async(
                    user_data['email'],
                    "Order Delivered – ShopEasy",
                    f"Hello {user_data['name']},\n\nYour order #{order_id} has been delivered successfully.\n\nThank you for shopping with us!\n\nShopEasy Team"
                )
    cursor2.close()
    cursor.close()
    db.close()
    return jsonify({"message": "Order status updated!"}), 200

# ─── ADMIN UPDATE PRODUCT ─────────────────────────────────
@app.route('/admin/product/update/<int:product_id>', methods=['PUT', 'OPTIONS'])
def update_product(product_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    name = data.get('name')
    description = data.get('description')
    price = data.get('price')
    stock = data.get('stock')
    category = data.get('category')
    discount = data.get('discount')
    rating = data.get('rating')
    images = data.get('images', [])
    return_days = data.get('return_days')
    images_json = json.dumps(images) if images else None

    db = get_db()
    cursor = db.cursor()
    query = "UPDATE products SET "
    params = []
    if name:
        query += "name = %s, "
        params.append(name)
    if description:
        query += "description = %s, "
        params.append(description)
    if price is not None:
        query += "price = %s, "
        params.append(price)
    if stock is not None:
        query += "stock = %s, "
        params.append(stock)
    if category:
        query += "category = %s, "
        params.append(category)
    if discount is not None:
        query += "discount = %s, "
        params.append(discount)
    if rating is not None:
        query += "rating = %s, "
        params.append(rating)
    if images_json is not None:
        query += "images = %s, "
        params.append(images_json)
    if return_days is not None:
        query += "return_days = %s, "
        params.append(return_days)
    query = query.rstrip(', ') + " WHERE id = %s"
    params.append(product_id)
    cursor.execute(query, params)
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Product updated successfully!"}), 200

# ─── USER PROFILE ROUTES ───────────────────────────────────
@app.route('/user/profile/<int:user_id>', methods=['GET'])
def get_user_profile(user_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, name, email, phone, address, city, pincode, state, latitude, longitude FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    db.close()
    return jsonify(user), 200

@app.route('/user/profile/update', methods=['PUT', 'OPTIONS'])
def update_user_profile():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    user_id = data['user_id']
    phone = data.get('phone')
    address = data.get('address')
    city = data.get('city')
    pincode = data.get('pincode')
    state = data.get('state')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE users SET phone = %s, address = %s, city = %s, pincode = %s, state = %s, 
        latitude = %s, longitude = %s
        WHERE id = %s
    """, (phone, address, city, pincode, state, latitude, longitude, user_id))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Profile updated successfully!"}), 200

# ─── PRODUCT DETAIL, RATING, COMMENT ROUTES ─────────────────
@app.route('/product/<int:product_id>', methods=['GET'])
def get_product_details(product_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()
    if not product:
        return jsonify({"error": "Product not found"}), 404
    if product.get('images'):
        product['images'] = json.loads(product['images'])
    else:
        product['images'] = []
    cursor.execute("SELECT AVG(rating) as avg_rating, COUNT(*) as total FROM product_ratings WHERE product_id = %s", (product_id,))
    rating_data = cursor.fetchone()
    product['avg_rating'] = float(rating_data['avg_rating']) if rating_data['avg_rating'] else 0
    product['total_ratings'] = rating_data['total'] or 0
    cursor.execute("""
        SELECT pc.id, pc.comment, pc.created_at, u.name as user_name
        FROM product_comments pc
        JOIN users u ON pc.user_id = u.id
        WHERE pc.product_id = %s
        ORDER BY pc.created_at DESC
    """, (product_id,))
    comments = cursor.fetchall()
    for c in comments:
        c['created_at'] = str(c['created_at'])
    cursor.close()
    db.close()
    return jsonify({"product": product, "comments": comments}), 200

@app.route('/product/rate', methods=['POST', 'OPTIONS'])
def rate_product():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    user_id = data['user_id']
    product_id = data['product_id']
    rating = data['rating']
    if rating < 1 or rating > 5:
        return jsonify({"error": "Rating must be between 1 and 5"}), 400
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM product_ratings WHERE user_id=%s AND product_id=%s", (user_id, product_id))
    existing = cursor.fetchone()
    if existing:
        cursor.execute("UPDATE product_ratings SET rating=%s WHERE user_id=%s AND product_id=%s", (rating, user_id, product_id))
    else:
        cursor.execute("INSERT INTO product_ratings (user_id, product_id, rating) VALUES (%s, %s, %s)", (user_id, product_id, rating))
    db.commit()
    cursor.execute("SELECT AVG(rating) as avg, COUNT(*) as cnt FROM product_ratings WHERE product_id=%s", (product_id,))
    stats = cursor.fetchone()
    cursor.execute("UPDATE products SET avg_rating=%s, total_ratings=%s WHERE id=%s", (stats[0], stats[1], product_id))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Rating submitted successfully!"}), 200

@app.route('/product/comment', methods=['POST', 'OPTIONS'])
def add_comment():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    user_id = data['user_id']
    product_id = data['product_id']
    comment = data['comment'].strip()
    if not comment:
        return jsonify({"error": "Comment cannot be empty"}), 400
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT INTO product_comments (user_id, product_id, comment) VALUES (%s, %s, %s)", (user_id, product_id, comment))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Comment added successfully!"}), 201

@app.route('/product/user-rating/<int:user_id>/<int:product_id>', methods=['GET'])
def get_user_rating(user_id, product_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT rating FROM product_ratings WHERE user_id=%s AND product_id=%s", (user_id, product_id))
    rating = cursor.fetchone()
    cursor.close()
    db.close()
    return jsonify({"rating": rating['rating'] if rating else 0}), 200

# ─── PRODUCT QUESTIONS & ANSWERS ────────────────────────────
@app.route('/product/questions/<int:product_id>', methods=['GET'])
def get_product_questions(product_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT pq.id, pq.question, pq.answer, pq.created_at, pq.answered_at,
               u.name as asker_name,
               a.name as answerer_name
        FROM product_questions pq
        JOIN users u ON pq.user_id = u.id
        LEFT JOIN users a ON pq.answered_by = a.id
        WHERE pq.product_id = %s
        ORDER BY pq.created_at DESC
    """, (product_id,))
    questions = cursor.fetchall()
    for q in questions:
        q['created_at'] = str(q['created_at'])
        if q['answered_at']:
            q['answered_at'] = str(q['answered_at'])
    cursor.close()
    db.close()
    return jsonify(questions), 200

@app.route('/product/ask', methods=['POST', 'OPTIONS'])
def ask_question():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    user_id = data['user_id']
    product_id = data['product_id']
    question = data['question'].strip()
    if not question:
        return jsonify({"error": "Question cannot be empty"}), 400
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO product_questions (product_id, user_id, question) VALUES (%s, %s, %s)",
        (product_id, user_id, question)
    )
    db.commit()
    
    cursor2 = db.cursor(dictionary=True)
    cursor2.execute("SELECT name FROM products WHERE id = %s", (product_id,))
    product = cursor2.fetchone()
    cursor2.close()
    product_name = product['name'] if product else "a product"
    
    admin_ids = get_admin_user_ids()
    for admin_id in admin_ids:
        create_notification(
            admin_id,
            'question',
            f'New question about {product_name}',
            f'User asked: "{question[:100]}"',
            f'/product/{product_id}'
        )
    
    cursor.close()
    db.close()
    return jsonify({"message": "Question posted successfully!"}), 201

@app.route('/product/answer/<int:question_id>', methods=['PUT', 'OPTIONS'])
def answer_question(question_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    admin_id = data['admin_id']
    answer = data['answer'].strip()
    if not answer:
        return jsonify({"error": "Answer cannot be empty"}), 400
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT user_id, product_id FROM product_questions WHERE id = %s", (question_id,))
    q_data = cursor.fetchone()
    if not q_data:
        return jsonify({"error": "Question not found"}), 404
    asker_user_id = q_data[0]
    product_id = q_data[1]
    
    cursor.execute("""
        UPDATE product_questions
        SET answer = %s, answered_by = %s, answered_at = NOW()
        WHERE id = %s
    """, (answer, admin_id, question_id))
    db.commit()
    
    create_notification(
        asker_user_id,
        'answer',
        'Your question was answered!',
        f'Admin answered: "{answer[:100]}"',
        f'/product/{product_id}'
    )
    
    cursor.close()
    db.close()
    return jsonify({"message": "Answer posted successfully!"}), 200

# ─── EDIT ANSWER (admin only) ─────────────────────────────
@app.route('/product/answer/edit/<int:question_id>', methods=['PUT', 'OPTIONS'])
def edit_answer(question_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    admin_id = data['admin_id']
    new_answer = data['answer'].strip()
    if not new_answer:
        return jsonify({"error": "Answer cannot be empty"}), 400
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM product_questions WHERE id = %s", (question_id,))
    if not cursor.fetchone():
        return jsonify({"error": "Question not found"}), 404
    cursor.execute("""
        UPDATE product_questions
        SET answer = %s, answered_by = %s, answered_at = NOW()
        WHERE id = %s
    """, (new_answer, admin_id, question_id))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Answer updated successfully!"}), 200

# ─── EDIT QUESTION (user only) ────────────────────────────
@app.route('/product/question/edit/<int:question_id>', methods=['PUT', 'OPTIONS'])
def edit_question(question_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    user_id = data['user_id']
    new_question = data['question'].strip()
    if not new_question:
        return jsonify({"error": "Question cannot be empty"}), 400
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT user_id FROM product_questions WHERE id = %s", (question_id,))
    result = cursor.fetchone()
    if not result:
        return jsonify({"error": "Question not found"}), 404
    if result[0] != user_id:
        return jsonify({"error": "You can only edit your own questions"}), 403
    cursor.execute("UPDATE product_questions SET question = %s WHERE id = %s", (new_question, question_id))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Question updated successfully!"}), 200

# ─── EDIT COMMENT (user only) ─────────────────────────────
@app.route('/product/comment/edit/<int:comment_id>', methods=['PUT', 'OPTIONS'])
def edit_comment(comment_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    user_id = data['user_id']
    new_comment = data['comment'].strip()
    if not new_comment:
        return jsonify({"error": "Comment cannot be empty"}), 400
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT user_id FROM product_comments WHERE id = %s", (comment_id,))
    result = cursor.fetchone()
    if not result:
        return jsonify({"error": "Comment not found"}), 404
    if result[0] != user_id:
        return jsonify({"error": "You can only edit your own comments"}), 403
    cursor.execute("UPDATE product_comments SET comment = %s WHERE id = %s", (new_comment, comment_id))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Comment updated successfully!"}), 200

# ─── NOTIFICATION ROUTES ───────────────────────────────────
@app.route('/notifications', methods=['GET'])
def get_notifications():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "User ID required"}), 400
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, type, title, message, link, is_read, created_at
        FROM notifications
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 50
    """, (user_id,))
    notifs = cursor.fetchall()
    for n in notifs:
        n['created_at'] = str(n['created_at'])
    cursor.close()
    db.close()
    return jsonify(notifs), 200

@app.route('/notifications/mark-read', methods=['PUT', 'OPTIONS'])
def mark_notifications_read():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    user_id = data['user_id']
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE notifications SET is_read = TRUE WHERE user_id = %s", (user_id,))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "All notifications marked as read"}), 200

@app.route('/notifications/mark-read/<int:notif_id>', methods=['PUT', 'OPTIONS'])
def mark_single_notification_read(notif_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.json
    user_id = data['user_id']
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s AND user_id = %s", (notif_id, user_id))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Notification marked as read"}), 200

# ─── ADMIN SALES DASHBOARD STATS ───
@app.route('/admin/sales-stats', methods=['GET'])
def get_sales_stats():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT 
            COALESCE(SUM(total_amount), 0) as total_sales,
            COUNT(*) as total_orders,
            COALESCE(COUNT(DISTINCT user_id), 0) as total_customers,
            COALESCE(AVG(total_amount), 0) as avg_order_value
        FROM orders WHERE status = 'delivered'
    """)
    summary = cursor.fetchone()
    
    cursor.execute("""
        SELECT 
            DATE(created_at) as date,
            COALESCE(SUM(total_amount), 0) as sales,
            COUNT(*) as orders
        FROM orders
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND status = 'delivered'
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    """)
    daily_sales = cursor.fetchall()
    
    cursor.execute("""
        SELECT 
            p.id,
            p.name,
            p.images,
            SUM(oi.quantity) as total_sold,
            SUM(oi.quantity * oi.price) as revenue
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.status = 'delivered'
        GROUP BY p.id
        ORDER BY total_sold DESC
        LIMIT 5
    """)
    top_products = cursor.fetchall()
    for p in top_products:
        if p.get('images'):
            img_list = json.loads(p['images'])
            p['image_url'] = img_list[0] if img_list else ''
        else:
            p['image_url'] = ''
    
    cursor.execute("""
        SELECT 
            status,
            COUNT(*) as count,
            COALESCE(SUM(total_amount), 0) as amount
        FROM orders
        GROUP BY status
    """)
    status_breakdown = cursor.fetchall()
    
    cursor.execute("""
        SELECT 
            DATE_FORMAT(created_at, '%Y-%m') as month,
            COALESCE(SUM(total_amount), 0) as sales,
            COUNT(*) as orders
        FROM orders
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 6 MONTH) AND status = 'delivered'
        GROUP BY DATE_FORMAT(created_at, '%Y-%m')
        ORDER BY month ASC
    """)
    monthly_sales = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return jsonify({
        'summary': summary,
        'daily_sales': daily_sales,
        'top_products': top_products,
        'status_breakdown': status_breakdown,
        'monthly_sales': monthly_sales
    }), 200

# ─── PRODUCT RECOMMENDATIONS (Collaborative Filtering) ───
@app.route('/product/recommendations/<int:product_id>', methods=['GET'])
def get_recommendations(product_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT DISTINCT order_id FROM order_items 
        WHERE product_id = %s
    """, (product_id,))
    order_ids = [row['order_id'] for row in cursor.fetchall()]
    if not order_ids:
        return jsonify([]), 200
    placeholders = ','.join(['%s'] * len(order_ids))
    cursor.execute(f"""
        SELECT 
            p.id, p.name, p.price, p.images, p.discount, p.rating,
            COUNT(*) as times_bought_together
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id IN ({placeholders}) 
          AND oi.product_id != %s
        GROUP BY oi.product_id
        ORDER BY times_bought_together DESC
        LIMIT 6
    """, order_ids + [product_id])
    recommendations = cursor.fetchall()
    for rec in recommendations:
        if rec.get('images'):
            rec['images'] = json.loads(rec['images'])
            rec['image_url'] = rec['images'][0] if rec['images'] else ''
        else:
            rec['image_url'] = ''
    cursor.close()
    db.close()
    return jsonify(recommendations), 200

# # ========== WEBSOCKET CHAT EVENTS ==========
# active_users = {}  # { user_id: { 'room': 'chat_userid', 'name': username } }

# @socketio.on('user_join')
# def handle_user_join(data):
#     print(f"🔵 user_join received: {data}")
#     user_id = data['user_id']
#     name = data.get('name', 'User')
#     room = f"chat_{user_id}"
#     join_room(room)
#     active_users[user_id] = {'room': room, 'name': name}
#     print(f"📋 Active users after join: {active_users}")
#     emit('active_users', {user_id: name}, broadcast=True)

# @socketio.on('admin_join')
# def handle_admin_join(data):
#     target_user = data['target_user']
#     room = f"chat_{target_user}"
#     join_room(room)
#     emit('admin_joined', {'message': 'Admin joined the chat'}, room=room)

# @socketio.on('chat_message')
# def handle_chat_message(data):
#     user_id = data['user_id']
#     message = data['message']
#     role = data.get('role', 'user')
#     room = f"chat_{user_id}"
#     emit('new_message', {
#         'user_id': user_id,
#         'role': role,
#         'message': message,
#         'timestamp': datetime.now().strftime('%H:%M')
#     }, room=room)

# @socketio.on('get_active_users')
# def handle_get_active_users():
#     print(f"📋 get_active_users called, active_users: {active_users}")
#     user_list = [{'id': uid, 'name': info['name']} for uid, info in active_users.items()]
#     emit('active_users_list', user_list)

# ─── START SERVER ─────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)