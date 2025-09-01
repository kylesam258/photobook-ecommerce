import os, json
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from jinja2 import Environment, FileSystemLoader
from mysql.connector import IntegrityError

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Set upload folder configuration
UPLOAD_FOLDER = 'uploads/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Connect to MySQL database
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="ecommerce_db_backup"
)

cursor = db.cursor()

# Decorators for authentication
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("You do not have access to this page.", 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Index Route (Homepage)
@app.route('/')
def index():
    return render_template('index.html')

# Signup Route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        try:
            name = request.form['name']
            email = request.form['email']
            password = request.form['password']
            
            # Check for existing name or email using a single query
            cursor.execute("""
                SELECT name, email FROM users 
                WHERE name = %s OR email = %s
                LIMIT 1
            """, (name, email))
            
            existing_user = cursor.fetchone()
            if existing_user:
                if existing_user[0] == name:
                    flash('That name is already taken. Please use a different name.', 'signup-error')
                else:
                    flash('That email is already registered. Please use a different email.', 'signup-error')
                return redirect(url_for('signup'))

            # Check if password is already in use
            cursor.execute("SELECT password FROM users")
            existing_passwords = cursor.fetchall()
            
            for existing_password in existing_passwords:
                if check_password_hash(existing_password[0], password):
                    flash('This password is already in use. Please choose a different password.', 'signup-error')
                    return redirect(url_for('signup'))

            # If no duplicates found, proceed with signup
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            cursor.execute(
                "INSERT INTO users (name, email, password, role, status) VALUES (%s, %s, %s, %s, %s)",
                (name, email, hashed_password, 'buyer', 'active')
            )
            db.commit()
            flash('Account created successfully! You can log in now.', 'signup-success')
            return redirect(url_for('signup'))
            
        except Exception as e:
            db.rollback()
            flash('An error occurred during signup. Please try again.', 'signup-error')
            return redirect(url_for('signup'))

    return render_template('signup.html')



# Assuming your uploads folder is at the root level of your project
UPLOAD_FOLDER = 'uploads' 
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Custom Jinja filter for images
@app.template_filter('image_path')
def image_path(filename):
    return url_for('uploaded_file', filename=filename)

app.jinja_env.filters['image_path'] = image_path

# View Document Route
@app.route('/view_document/<document_id>', methods=['GET'])
def view_document(document_id):
    return send_from_directory('uploads', document_id)

# Admin Dashboard Route
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Fetch seller requests
    cursor.execute(""" 
        SELECT 
            id, 
            business_name, 
            contact_number, 
            email, 
            id_proof, 
            profile_description, 
            payment_details, 
            product_photo 
        FROM seller_requests 
        WHERE status = 'pending'
    """)
    seller_requests = [
        {
            'id': row[0],
            'business_name': row[1],
            'contact_number': row[2],
            'email': row[3],
            'id_proof': row[4],
            'profile_description': row[5],
            'payment_details': row[6],
            'product_photo': row[7]
        }
        for row in cursor.fetchall()
    ]

    # Fetch registered users
    cursor.execute("""
        SELECT 
            id, 
            name, 
            email,
            role, 
            status 
        FROM users  -- Replace with your actual user table name
    """)
    users = [
        {
            'id': row[0],
            'username': row[1],
            'email': row[2],
            'role': row[3],
            'status': row[4]
        }
        for row in cursor.fetchall()
    ]

    return render_template('admin_dashboard.html', seller_requests=seller_requests, users=users)

# Archive User Route
@app.route('/admin/archive_user/<int:user_id>', methods=['POST'])
@admin_required
def archive_user(user_id):
    try:
        cursor.execute("UPDATE users SET status = 'archived' WHERE id = %s", (user_id,))
        db.commit()
        flash('User archived successfully!', 'admin-success')
    except mysql.connector.Error as err:
        flash(f"Error: {err}", 'admin-danger')
    return redirect(url_for('admin_dashboard'))


@app.route('/unarchive_user/<int:user_id>', methods=['POST'])
def unarchive_user(user_id):
    try:
        # Query to update the user status to active
        query = "UPDATE users SET status = 'active' WHERE id = %s"
        cursor.execute(query, (user_id,))
        db.commit()  # Commit the changes to the database

        if cursor.rowcount > 0:
            flash('User has been unarchived successfully', 'admin-success')
        else:
            flash('User not found or already active', 'admin-error')
    except mysql.connector.Error as err:
        flash(f"Error: {err}", 'admin-danger')

    return redirect(url_for('admin_dashboard'))  # Replace 'admin_dashboard' with your dashboard route


# Approve Seller Request
@app.route('/admin/approve_request/<int:request_id>', methods=['GET'])
@admin_required
def approve_request(request_id):
    try:
        # Check if the seller request exists
        cursor.execute("SELECT user_id FROM seller_requests WHERE id = %s", (request_id,))
        result = cursor.fetchone()

        if result:
            user_id = result[0]
            # Begin transaction
            cursor.execute("UPDATE users SET role = 'seller' WHERE id = %s", (user_id,))
            cursor.execute("UPDATE seller_requests SET status = 'approved' WHERE id = %s", (request_id,))
            db.commit()  # Commit the changes
            flash('Seller request approved successfully!', 'admin-success')
        else:
            flash('Request not found!', 'admin-error')
    except mysql.connector.Error as err:
        db.rollback()  # Roll back any changes on error
        flash(f"Error: {err}", 'admin-danger')

    return redirect(url_for('admin_dashboard'))


# Reject Seller Request
@app.route('/admin/reject_request/<int:request_id>', methods=['GET'])
@admin_required
def reject_request(request_id):
    try:
        # Check if the seller request exists
        cursor.execute("SELECT id FROM seller_requests WHERE id = %s", (request_id,))
        result = cursor.fetchone()

        if result:
            # Update the status to 'rejected'
            cursor.execute("UPDATE seller_requests SET status = 'rejected' WHERE id = %s", (request_id,))
            db.commit()  # Commit the changes
            flash('Seller request rejected successfully!', 'admin-success')
        else:
            flash('Request not found!', 'admin-error')
    except mysql.connector.Error as err:
        db.rollback()  # Roll back any changes on error
        flash(f"Error: {err}", 'admin-danger')

    return redirect(url_for('admin_dashboard'))


@app.route('/change_role/<int:user_id>', methods=['POST'])
def change_role(user_id):
    new_role = request.form.get('role')
    cursor = db.cursor()

    # Update the user's role in the database
    try:
        cursor.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
        db.commit()
        flash(f'Role updated to {new_role} for user with ID {user_id}', 'success')
    except mysql.connector.Error as err:
        db.rollback()
        flash(f'Error updating role: {err}', 'error')
    finally:
        cursor.close()

    return redirect(url_for('admin_dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        cursor.execute("SELECT id, name, password, role, status FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if user and user[4] == 'active' and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['name'] = user[1]
            session['role'] = user[3]
            flash('Welcome, log in to get started!', 'login-success')
            
            # If the user came from a specific page, redirect them back
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
                
            # Default redirect based on role
            if user[3] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user[3] == 'seller':
                return redirect(url_for('seller_dashboard'))
            else:
                return redirect(url_for('buyer_dashboard'))
        else:
            flash('Invalid credentials or inactive account. Please try again.', 'login-danger')
    return render_template('login.html')

# seller Dashboard Route
@app.route('/seller_dashboard')
@login_required
def seller_dashboard():
    # Create cursor
    cursor = db.cursor(dictionary=True)
    
    # Get user_id of logged in seller
    user_id = session['user_id']
    
    cursor.execute("""
        SELECT COUNT(DISTINCT o.id) as active_orders
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN products p ON oi.product_id = p.id
        WHERE oi.seller_status = 'Shipped' AND p.user_id = %s
    """, (user_id,))
    active_orders = cursor.fetchone()['active_orders'] or 0
    
    cursor.execute("""
        SELECT SUM(stock) as total_stock
        FROM products 
        WHERE user_id = %s AND is_archive = 0
    """, (user_id,))
    total_stock = cursor.fetchone()['total_stock'] or 0
    
    # Get current seller's pending orders count
    cursor.execute("""
        SELECT COUNT(DISTINCT o.id) as count
        FROM orders o 
        JOIN order_items oi ON o.id = oi.order_id
        JOIN products p ON oi.product_id = p.id
        WHERE p.user_id = %s AND oi.seller_status = 'Pending'
    """, (user_id,))
    pending_orders_count = cursor.fetchone()['count']

    # Get total sales for this specific seller
    cursor.execute("""
        SELECT SUM(oi.quantity * oi.price) AS total_sales 
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.seller_status = 'Delivered' 
        AND p.user_id = %s
    """, (user_id,))
    result = cursor.fetchone()
    total_sales = result['total_sales'] if result['total_sales'] is not None else 0

    # Get user's products
    cursor.execute("SELECT * FROM products WHERE user_id = %s", (user_id,))
    products_dicts = cursor.fetchall()
    
    # Close cursor and commit changes
    cursor.close()
    db.commit()
    
    return render_template('seller_dashboard.html', 
                         products=products_dicts,
                         pending_orders_count=pending_orders_count,
                         active_orders=active_orders,
                         total_stock=total_stock,
                         total_sales=total_sales)

@app.route('/seller_account_settings')
def seller_account_settings():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard.', 'danger')
        return redirect(url_for('login'))

    # Retrieve the user's name from the session
    user_name = session.get('name')  # Use 'name' stored in session
    return render_template('seller_account_settings.html', user_name=user_name)


@app.route('/archive_product/<int:product_id>', methods=['POST'])
@login_required
def archive_product(product_id):
    cursor.execute("UPDATE products SET is_archive = 1 WHERE id = %s", (product_id,))
    db.commit()
    flash('Product has been marked as deleted.', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/unarchive_product/<int:product_id>', methods=['POST'])
@login_required
def unarchive_product(product_id):
    cursor.execute("UPDATE products SET is_archive = 0 WHERE id = %s", (product_id,))
    db.commit()
    flash('Product has been restored.', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/seller_orders')
@login_required
def seller_orders():
    seller_id = session['user_id']
    cursor = db.cursor(dictionary=True)

    query = """
    SELECT 
        o.id AS order_id,
        oi.seller_status AS status,
        o.created_at,
        o.payment_method,
        u.name AS buyer_name,
        u.email AS buyer_email,
        a.address AS buyer_address,
        GROUP_CONCAT(p.product_name) AS product_names,
        GROUP_CONCAT(oi.quantity) AS quantities,
        GROUP_CONCAT(oi.price) AS prices,
        GROUP_CONCAT(p.size) AS sizes,
        GROUP_CONCAT(p.pages) AS pages
    FROM orders o
    JOIN order_items oi ON o.id = oi.order_id
    JOIN products p ON oi.product_id = p.id AND p.user_id = %s  
    JOIN users u ON o.user_id = u.id
    JOIN addresses a ON o.address_id = a.id
    GROUP BY o.id
    ORDER BY o.created_at DESC
    """
    
    cursor.execute(query, (seller_id,))
    orders = cursor.fetchall()

    # Process the grouped data
    processed_orders = []
    for order in orders:
        # Check if any of the GROUP_CONCAT results are None
        if (order['product_names'] is None or 
            order['quantities'] is None or 
            order['prices'] is None or 
            order['sizes'] is None or 
            order['pages'] is None):
            continue

        order['products'] = []
        try:
            product_names = order['product_names'].split(',')
            quantities = order['quantities'].split(',')
            prices = order['prices'].split(',')
            sizes = order['sizes'].split(',')
            pages = order['pages'].split(',')
            
            for i in range(len(product_names)):
                order['products'].append({
                    'name': product_names[i],
                    'quantity': quantities[i],
                    'price': prices[i],
                    'size': sizes[i],
                    'pages': pages[i]
                })
            processed_orders.append(order)
        except (AttributeError, IndexError) as e:
            print(f"Error processing order {order['order_id']}: {str(e)}")
            continue

    return render_template('seller_orders.html', orders=processed_orders)

@app.route('/update_order_status', methods=['POST'])
@login_required
def update_order_status():
    seller_id = session['user_id']
    order_id = request.form.get('order_id')
    new_status = request.form.get('status')

    cursor = db.cursor()
    
    # Update only the order items that belong to this seller
    update_query = """
        UPDATE order_items oi
        JOIN products p ON oi.product_id = p.id
        SET oi.seller_status = %s
        WHERE oi.order_id = %s AND p.user_id = %s
    """
    cursor.execute(update_query, (new_status, order_id, seller_id))
    db.commit()

    # Check if all sellers have marked their items as delivered
    # Only then update the main order status
    if new_status == 'Delivered':
        check_query = """
            SELECT COUNT(*) = 0 as all_delivered
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = %s AND oi.seller_status != 'Delivered'
        """
        cursor.execute(check_query, (order_id,))
        result = cursor.fetchone()
        if result[0]:  # If all items are delivered
            cursor.execute("UPDATE orders SET status = 'Delivered' WHERE id = %s", (order_id,))
            db.commit()

    flash(f'Order #{order_id} status updated to {new_status}.', 'success')
    return redirect(url_for('seller_orders'))


# Buyer Dashboard Route
@app.route('/buyer_dashboard')
@login_required
def buyer_dashboard():
    # Allow both buyers and sellers to access this page
    if session.get('role') not in ['buyer', 'seller']:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))

    cursor = db.cursor()

    # Fetch all categories for the dropdown
    cursor.execute("SELECT id, name FROM categories")
    categories = cursor.fetchall()

    # Get the selected category ID from query parameters (default is "all")
    category_id = request.args.get('category_id', 'all')

    # Get the search query from query parameters
    search_query = request.args.get('query', '')

    # Fetch products based on the selected category and search query
    if search_query:
        if category_id == 'all':
            cursor.execute("""
                SELECT * 
                FROM products 
                WHERE is_archive = 0 AND (product_name LIKE %s OR size LIKE %s OR price LIKE %s)
            """, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
        else:
            cursor.execute("""
                SELECT * 
                FROM products 
                WHERE is_archive = 0 AND category_id = %s 
                AND (product_name LIKE %s OR size LIKE %s)
            """, (category_id, f"%{search_query}%", f"%{search_query}%"))
    else:
        if category_id == 'all':
            cursor.execute("SELECT * FROM products WHERE is_archive = 0")
        else:
            cursor.execute("""
                SELECT * 
                FROM products 
                WHERE is_archive = 0 AND category_id = %s
            """, (category_id,))

    products = cursor.fetchall()

    # Convert products into dictionaries for easy template rendering
    column_names = [desc[0] for desc in cursor.description]
    products_dicts = [dict(zip(column_names, product)) for product in products]

    cursor.close()

    # Pass products, categories, the selected category, and search query to the template
    return render_template(
        'buyer_dashboard.html', 
        products=products_dicts, 
        categories=categories, 
        selected_category=category_id,  # Pass the selected category
        search_query=search_query  # Pass the search query
    )

# Seller Registration Form
@app.route('/seller_registration')
@login_required
def seller_registration():
    # Prevent sellers from accessing seller registration
    if session.get('role') == 'seller':
        flash('You are already registered as a seller.', 'warning')
        return redirect(url_for('buyer_dashboard'))
    
    return render_template('seller_registration.html')

# Seller Registration Submission Route
def save_file(file):
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        return filename
    return None

@app.route('/submit_seller_registration', methods=['POST'])
@login_required
def submit_seller_registration():
    user_id = session['user_id']
    business_name = request.form.get('business_name')
    contact_number = request.form.get('contact_number')
    email = request.form.get('email')
    profile_description = request.form.get('profile_description')
    payment_details = request.form.get('payment_details')

    id_proof = request.files.get('id_proof')
    product_photo = request.files.get('product_photo')

    id_proof_filename = save_file(id_proof)
    product_photo_filename = save_file(product_photo)

    try:
        cursor.execute(""" 
            INSERT INTO seller_requests 
            (user_id, business_name, contact_number, email, id_proof, profile_description, payment_details, product_photo, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """, (user_id, business_name, contact_number, email, id_proof_filename, profile_description, payment_details, product_photo_filename))
        db.commit()
        flash('Your seller registration request has been submitted!', 'success')
    except mysql.connector.Error as err:
        flash(f"Error: {err}", 'danger')
    
    return redirect(url_for('buyer_dashboard'))

#edit product
@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if request.method == 'GET':
        # Fetch product details
        cursor.execute("SELECT id, product_name, size, pages, stock, price FROM products WHERE id = %s", (product_id,))
        product = cursor.fetchone()
        if not product:
            return "Product not found", 404
        return render_template('edit_product.html', product=product)
    
    elif request.method == 'POST':
        # Update product details
        product_name = request.form['product_name']
        size = request.form['size']
        pages = request.form['pages']
        stock = request.form['stock']
        price = request.form['price']

        cursor.execute("""
            UPDATE products 
            SET product_name = %s, size = %s, pages = %s, stock = %s, price = %s
            WHERE id = %s
        """, (product_name, size, pages, stock, price, product_id))
        db.commit()

        return redirect(url_for('seller_dashboard'))  # Redirect to the seller dashboard
# add product route
@app.route('/add_product_page')
def add_product_page():
    return render_template('add_product.html')
@app.route('/add_product', methods=['POST'])
@login_required  # Ensure user is logged in before adding a product
def add_product():
    if request.method == 'POST':
        # Retrieve the user_id from the session
        user_id = session.get('user_id')

    product_name = request.form['product_name']
    size = request.form['size']
    pages = request.form['pages']
    stock = request.form['stock']
    price = request.form['price']
    category_id = request.form.get('category_id')  # Existing category
    new_category_name = request.form.get('new_category_name')  # For a new category
    image = request.files['image']  # The uploaded image file

    # Handle image upload
    if image:
        filename = secure_filename(image.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(file_path)  # Save the image to the uploads folder
    else:
        filename = None  # Handle case where no image is provided

    try:
        # If a new category name is provided, insert it into the categories table and retrieve the ID
        if new_category_name:
            cursor.execute("INSERT INTO categories (name) VALUES (%s)", (new_category_name,))
            db.commit()
            category_id = cursor.lastrowid  # Get the ID of the newly added category

        # Insert the product into the database
        cursor.execute("""
            INSERT INTO products (user_id, product_name, size, pages, stock, price, image_path, category_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, product_name, size, pages, stock, price, filename, category_id))
        db.commit()
        flash('Product added successfully!', 'success')
    except mysql.connector.Error as err:
        flash(f"Error: {err}", 'danger')

    return redirect('/seller_dashboard')  # Redirect back to the seller dashboard or another appropriate page

#cart
@app.route('/cart')
@login_required
def cart():
    user_id = session['user_id']  # Ensure you're getting the logged-in user's ID

    cursor = db.cursor()

    # Fetch cart items with product details for the logged-in user
    cursor.execute("""
        SELECT 
            ci.product_id AS id,
            p.product_name AS name,
            p.price AS price,
            ci.quantity AS quantity
        FROM 
            cart_items ci
        JOIN 
            products p ON ci.product_id = p.id
        WHERE 
            ci.user_id = %s
    """, (user_id,))

    cart_items = cursor.fetchall()

    # Calculate total price
    total_price = sum(item[2] * item[3] for item in cart_items)  # price * quantity

    # Convert to dictionaries for easy rendering
    column_names = [desc[0] for desc in cursor.description]
    cart_items_dict = [dict(zip(column_names, item)) for item in cart_items]

    cursor.close()

    return render_template(
        'cart.html',
        cart_items=cart_items_dict,
        total_price=total_price
    )


#add to cart
@app.route('/_cart', methods=['POST'])
@login_required
def add_to_cart():
    user_id = session['user_id']
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))

    cursor = db.cursor()

    # Check if the product is already in the cart
    cursor.execute("""
        SELECT id, quantity FROM cart_items 
        WHERE user_id = %s AND product_id = %s
    """, (user_id, product_id))
    cart_item = cursor.fetchone()

    if cart_item:
        # Update quantity
        new_quantity = cart_item[1] + quantity
        cursor.execute("""
            UPDATE cart_items 
            SET quantity = %s 
            WHERE id = %s
        """, (new_quantity, cart_item[0]))
    else:
        # Add new cart item
        cursor.execute("""
            INSERT INTO cart_items (user_id, product_id, quantity)
            VALUES (%s, %s, %s)
        """, (user_id, product_id, quantity))

    db.commit()
    flash('Product added to cart.', 'success')
    return redirect(url_for('cart'))

#update cart
@app.route('/update_cart', methods=['POST'])
@login_required
def update_cart():
    # Get form data
    product_id = request.form.get('product_id')
    quantity = request.form.get('quantity')

    if not product_id or not quantity:
        flash('Invalid data provided.', 'danger')
        return redirect(url_for('view_cart'))

    # Update the cart item in the database
    try:
        cursor = db.cursor()
        cursor.execute("""
            UPDATE cart_items 
            SET quantity = %s 
            WHERE product_id = %s AND user_id = %s
        """, (quantity, product_id, session['user_id']))
        db.commit()
        cursor.close()
        flash('Cart updated successfully.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Error updating cart: {e}', 'danger')

    return redirect(url_for('cart'))

#remove from cart
@app.route('/remove_from_cart', methods=['POST'])
@login_required
def remove_from_cart():
    product_id = request.form.get('product_id')

    if not product_id:
        flash('Invalid product ID.', 'danger')
        return redirect(url_for('cart'))

    try:
        cursor = db.cursor()
        cursor.execute("""
            DELETE FROM cart_items 
            WHERE product_id = %s AND user_id = %s
        """, (product_id, session['user_id']))
        db.commit()
        cursor.close()
        flash('Item removed from cart.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Error removing item: {e}', 'danger')

    return redirect(url_for('cart'))

#checkout
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    user_id = session['user_id']
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        # Get selected items from form
        selected_items = json.loads(request.form.get('selected_items', '[]'))
        
        # Fetch only selected cart items
        if selected_items:
            # Create placeholders for SQL IN clause
            placeholders = ', '.join(['%s'] * len(selected_items))
            query = f"""
                SELECT c.product_id, c.quantity, p.product_name, p.price, (c.quantity * p.price) as total 
                FROM cart_items c
                JOIN products p ON c.product_id = p.id
                WHERE c.user_id = %s AND c.product_id IN ({placeholders})
            """
            # Create parameters tuple with user_id and selected items
            params = (user_id,) + tuple(selected_items)
            cursor.execute(query, params)
        else:
            return redirect(url_for('cart'))
    else:
        # If GET request, fetch all cart items
        cursor.execute("""
            SELECT c.product_id, c.quantity, p.product_name, p.price, (c.quantity * p.price) as total 
            FROM cart_items c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = %s
        """, (user_id,))

    cart_items = cursor.fetchall()
    
    if not cart_items:
        flash('No items selected for checkout', 'warning')
        return redirect(url_for('cart'))

    # Calculate total price of selected items
    total_price = sum(item['total'] for item in cart_items)

    # Fetch addresses
    cursor.execute("SELECT id, address FROM addresses WHERE user_id = %s", (user_id,))
    addresses = cursor.fetchall()

    return render_template('checkout.html', 
                         cart_items=cart_items,
                         addresses=addresses, 
                         total_price=total_price)

# place order
@app.route('/place_order', methods=['POST'])
@login_required
def place_order():
    user_id = session['user_id']
    address_id = request.form.get('address_id')
    payment_method = request.form.get('payment_method')

    cursor = db.cursor(dictionary=True)

    try:
        # Start transaction
        cursor.execute("START TRANSACTION")

        # Create the order
        cursor.execute("""
            INSERT INTO orders (user_id, address_id, payment_method, status, total_amount)
            VALUES (%s, %s, %s, 'Pending', 0)
        """, (user_id, address_id, payment_method))
        order_id = cursor.lastrowid

        # Get selected items from cart and insert into order_items
        cursor.execute("""
            SELECT c.product_id, c.quantity, p.price
            FROM cart_items c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = %s
        """, (user_id,))
        cart_items = cursor.fetchall()

        total_amount = 0
        for item in cart_items:
            cursor.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, price)
                VALUES (%s, %s, %s, %s)
            """, (order_id, item['product_id'], item['quantity'], item['price']))
            total_amount += item['quantity'] * item['price']

        # Update order total
        cursor.execute("UPDATE orders SET total_amount = %s WHERE id = %s", 
                      (total_amount, order_id))

        # Remove purchased items from cart
        cursor.execute("DELETE FROM cart_items WHERE user_id = %s", (user_id,))

        # Commit transaction
        cursor.execute("COMMIT")
        flash("Order placed successfully!", "success")
        return redirect(url_for('orders_dashboard'))

    except Exception as e:
        cursor.execute("ROLLBACK")
        flash(f"Error placing order: {str(e)}", "error")
        return redirect(url_for('checkout'))


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

#add category
@app.route('/add_category', methods=['POST'])
def add_category():
    new_category = request.json.get('category_name')  # Expecting JSON payload
    if not new_category:
        return jsonify({"error": "Category name is required"}), 400

    try:
        cursor.execute("INSERT INTO categories (name) VALUES (%s)", (new_category,))
        db.commit()

        # Retrieve the ID of the newly inserted category
        new_category_id = cursor.lastrowid
        return jsonify({"id": new_category_id, "name": new_category}), 200
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500


@app.route('/categories', methods=['GET'])
def get_categories():
    cursor.execute("SELECT * FROM categories")
    categories = cursor.fetchall()
    category_list = [{'id': category[0], 'name': category[1]} for category in categories]
    return jsonify(category_list)
    
# Logout Route
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# orders dashboard Routes
@app.route('/orders_dashboard')
def orders_dashboard():
    # Retrieve the user_id from session (after login)
    user_id = session.get('user_id')

    if not user_id:
        flash('Please log in first.', 'login-warning')
        return redirect(url_for('login'))  # Redirect to login if no user_id is found in 
    
    db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="ecommerce_db_backup"
    )

    cursor = db.cursor(dictionary=True)

    # Fetch all orders for the user, including product details
    cursor.execute("""
    SELECT o.id AS order_id, o.status, o.total_amount, o.created_at, 
           p.product_name, p.size, p.pages, oi.quantity 
    FROM orders o
    JOIN order_items oi ON o.id = oi.order_id
    JOIN products p ON oi.product_id = p.id
    WHERE o.user_id = %s
    """, (user_id,))
    orders = cursor.fetchall()

    # Separate orders into sections based on status
    pending_orders = [order for order in orders if order['status'] == 'Pending']
    shipped_orders = [order for order in orders if order['status'] == 'Shipped']
    delivered_orders = [order for order in orders if order['status'] == 'Delivered']
    cancelled_orders = [order for order in orders if order['status'] == 'Cancelled']

    # Return the template and pass the orders data
    return render_template('orders_dashboard.html', 
                           pending_orders=pending_orders,
                           shipped_orders=shipped_orders,
                           delivered_orders=delivered_orders,
                           cancelled_orders=cancelled_orders)

@app.route('/cancel_order/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    cursor = db.cursor()

    # Print the order ID to ensure it's correct
    print(f"Cancelling order with ID: {order_id}")

    # Update the order status to 'Cancelled' in the database
    cursor.execute("UPDATE orders SET status = 'Cancelled' WHERE id = %s", (order_id,))
    db.commit()

    flash('Your order has been cancelled.', 'success')
    return redirect(url_for('orders_dashboard'))

#addresess dashboard
@app.route('/addresses_dashboard')
def addresses_dashboard():
    user_id = session.get('user_id')  # Ensure the logged-in user's ID is retrieved
    if not user_id:
        return redirect('/login')

    conn = mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='ecommerce_db_backup'
    )
    cursor = conn.cursor(dictionary=True)

    # Fetch addresses for the logged-in user
    cursor.execute("SELECT id, name, address, phone FROM addresses WHERE user_id = %s", (user_id,))
    addresses = cursor.fetchall()

    conn.close()
    return render_template('addresses_dashboard.html', addresses=addresses)

#add address
@app.route('/add_address', methods=['GET', 'POST'])
def add_address():
    if request.method == 'POST':
        # Get data from the form
        name = request.form['name']
        address = request.form['address']
        phone = request.form['phone']

        # Assume user_id is stored in session after login (example: session['user_id'])
        user_id = session.get('user_id')  # Make sure the user is logged in

        if user_id:
            # Insert the data into the addresses table
            cursor.execute("INSERT INTO addresses (user_id, name, address, phone) VALUES (%s, %s, %s, %s)",
                           (user_id, name, address, phone))
            db.commit()

            # Redirect to address dashboard or another page
            return redirect(url_for('addresses_dashboard'))
        else:
            return redirect(url_for('login'))  # If not logged in, redirect to login page

    return render_template('add_address.html')

#delete address
@app.route('/delete_address/<int:address_id>', methods=['POST'])
def delete_address(address_id):
    user_id = session.get('user_id')  # Ensure the user is logged in
    if user_id:
        try:
            # Delete the address from the database
            cursor.execute("DELETE FROM addresses WHERE id = %s AND user_id = %s", (address_id, user_id))
            db.commit()
            flash("Address deleted successfully.", "success")
        except Exception as e:
            db.rollback()
            flash("Failed to delete address. Please try again.", "danger")
    else:
        flash("You must be logged in to delete addresses.", "warning")
    
    return redirect(url_for('addresses_dashboard'))


@app.route('/account_settings_dashboard')
@login_required
def account_settings_dashboard():
    # Only allow buyers to access account settings from buyer dashboard
    if session.get('role') == 'seller':
        flash('Please use the seller dashboard for account settings.', 'warning')
        return redirect(url_for('buyer_dashboard'))
    
    user_id = session.get('user_id')
    cursor.execute("SELECT name, email FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    return render_template('account_settings_dashboard.html', user=user)

@app.route('/update-profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return jsonify({'message': 'User not logged in!'}), 401

    data = request.json
    name = data.get('name')
    email = data.get('email')
    user_id = session['user_id']  # Retrieve user ID from session

    if not name or not email:
        return jsonify({'message': 'Name and email are required!'}), 400

    try:
        cursor = db.cursor()
        cursor.execute("UPDATE users SET name = %s, email = %s WHERE id = %s", (name, email, user_id))
        db.commit()
        return jsonify({'message': 'Profile updated successfully!'})
    except mysql.connector.Error as err:
        print(err)
        return jsonify({'message': 'An error occurred updating the profile.'}), 500
    finally:
        cursor.close()

@app.route('/change-password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'message': 'User not logged in!'}), 401

    data = request.json
    current_password = data.get('currentPassword')
    new_password = data.get('newPassword')

    if not current_password or not new_password:
        return jsonify({'message': 'Both current and new passwords are required!'}), 400

    try:
        cursor = db.cursor(dictionary=True)
        user_id = session['user_id']

        # Fetch the current hashed password from the database
        cursor.execute("SELECT password FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user or not check_password_hash(user['password'], current_password):
            return jsonify({'message': 'Current password is incorrect!'}), 403

        # Hash the new password
        hashed_password = generate_password_hash(new_password)

        # Update the password in the database
        cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, user_id))
        db.commit()

        return jsonify({'message': 'Password changed successfully!'})
    except mysql.connector.Error as err:
        print(err)
        return jsonify({'message': 'An error occurred while changing the password.'}), 500
    finally:
        cursor.close()

@app.route('/update_seller_account', methods=['POST'])
@login_required
def update_seller_account():
    if request.method == 'POST':
        try:
            # Get form data
            new_name = request.form['name']
            new_email = request.form['email']
            new_password = request.form['password']
            
            cursor = db.cursor(dictionary=True)
            
            # Check if email already exists (excluding current user)
            cursor.execute("SELECT id FROM users WHERE email = %s AND id != %s", 
                         (new_email, session['user_id']))
            if cursor.fetchone():
                flash('Email already exists!', 'account_error')  # Changed category
                return redirect(url_for('seller_account_settings'))
            
            # Update query
            if new_password:
                # Update with new password
                hashed_password = generate_password_hash(new_password)
                cursor.execute("""
                    UPDATE users 
                    SET name = %s, email = %s, password = %s 
                    WHERE id = %s
                """, (new_name, new_email, hashed_password, session['user_id']))
            else:
                # Update without changing password
                cursor.execute("""
                    UPDATE users 
                    SET name = %s, email = %s 
                    WHERE id = %s
                """, (new_name, new_email, session['user_id']))
            
            db.commit()
            
            # Update session
            session['name'] = new_name
            session['email'] = new_email
            
            flash('Account settings updated successfully!', 'account_success')  # Changed category
            
        except Exception as e:
            db.rollback()
            print(f"Error: {str(e)}")
            flash('An error occurred while updating your account.', 'account_error')  # Changed category
            
        finally:
            cursor.close()
            
    return redirect(url_for('seller_account_settings'))

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy-policy.html')

@app.route('/terms-of-service')
def terms_of_service():
    return render_template('terms-of-service.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    return render_template('contact.html')

if __name__ == '__main__':
    app.run(debug=True)
    