import os
import json
import random
from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify
import mysql.connector
import bcrypt
from werkzeug.utils import secure_filename
import secrets
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv  # Added for environment variables
import logging
from logging.handlers import RotatingFileHandler
import traceback
import time
import socket
from contextlib import contextmanager
from markupsafe import escape


# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['DEBUG'] = True  # Set back to True for local development

# Use environment variables for sensitive data
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_secret_key')

UPLOAD_FOLDER = 'static/uploads/'
AVATAR_FOLDER = 'static/avatars/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

AVATARS = [
    "female1.jpg", "female2.jpg", "female3.jpg", "female4.jpg",
    "male1.jpg", "male2.jpg", "male3.jpg", "male4.jpg"
]

# Ensure avatar files exist
def ensure_default_avatars():
    avatars_path = os.path.join(app.static_folder, 'avatars')
    os.makedirs(avatars_path, exist_ok=True)
    for avatar in AVATARS:
        default_path = os.path.join('default_avatars', avatar)
        target_path = os.path.join(avatars_path, avatar)
        if os.path.exists(default_path) and not os.path.exists(target_path):
            shutil.copy(default_path, target_path)

ensure_default_avatars()

RURAL_JOB_TITLES = [
    "Farmer", "Daily Laborer", "Animal Caretaker", "Tractor Driver",
    "Irrigation Technician", "Crop Harvester", "Fertilizer Sprayer",
    "Agri Equipment Mechanic", "Field Supervisor", "Poultry Worker",
    "Beekeeper", "Fisherman", "Dairy Farmer", "Organic Farmer",
    "Greenhouse Worker", "Agricultural Scientist", "Soil Tester",
    "Water Resource Manager", "Farm Equipment Operator", "Seed Distributor"
]

def ensure_upload_dirs():
    for directory in [UPLOAD_FOLDER, AVATAR_FOLDER]:
        os.makedirs(directory, exist_ok=True)

ensure_upload_dirs()

@contextmanager
def get_db_connection():
    conn = None
    try:
        # Get database configuration with proper defaults and explicit password
        db_config = {
            'host': os.getenv('DB_HOST', 'mysql.railway.internal'),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD','payBGkxifWTJqncDMjpiYCjKVUzuOxwD'),  # This is required
            'database': os.getenv('DB_NAME', 'railway'),
            'port': int(os.getenv('DB_PORT', '3306')),
            'auth_plugin': 'mysql_native_password',
            'connect_timeout': 30,
            'use_pure': True,
            'allow_local_infile': True,
            'raise_on_warnings': True
        }
        
        # Log connection attempt without exposing password
        app.logger.info(f"Attempting database connection to {db_config['host']}:{db_config['port']} as {db_config['user']}")
        
        if not db_config['password']:
            raise ValueError("Database password not set in environment variables")
            
        conn = mysql.connector.connect(**db_config)
        conn.ping(reconnect=True, attempts=3, delay=5)
        yield conn
        
    except mysql.connector.Error as e:
        app.logger.error(f"Database connection failed: {str(e)}")
        if conn and conn.is_connected():
            conn.rollback()
        raise
    except ValueError as e:
        app.logger.error(f"Configuration error: {str(e)}")
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()
            app.logger.info("Database connection closed")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_translations(lang):
    try:
        with open(f'translations/{lang}.json', 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        with open('translations/en.json', 'r', encoding='utf-8') as file:
            return json.load(file)

@app.context_processor
def utility_processor():
    def get_text(key, *args, **kwargs):
        lang = session.get('language', 'en')
        translations = load_translations(lang)
        text = translations.get(key, key)
        if args or kwargs:
            return text % (args or kwargs)
        return text

    saved_count = 0
    if 'user_id' in session:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM bookmarks WHERE user_id = %s", (session['user_id'],))
            saved_count = cursor.fetchone()[0]
            cursor.close()

    return dict(get_text=get_text, saved_count=saved_count)

@app.route('/change_language/<lang>')
def change_language(lang):
    if lang in ['en', 'hi', 'te']:
        session['language'] = lang
    return redirect(request.referrer or url_for('index'))

@app.route('/')
def home():
    return render_template("login.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            login_id = request.form['login_id']
            password = request.form['password']

            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT * FROM users WHERE username = %s OR phone_number = %s", 
                             (login_id, login_id))
                user = cursor.fetchone()
                cursor.close()

                if user and bcrypt.checkpw(password.encode(), user['password'].encode()):
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    return redirect(url_for('dashboard'))
                else:
                    flash("Incorrect Password or Username/Phone", "danger")
                    return redirect(url_for('home'))

        except mysql.connector.Error as e:
            app.logger.error(f"Database error during login: {e}")
            flash("Unable to process login. Please try again.", "error")
            return redirect(url_for('home'))

    return render_template('login.html')

@app.route('/login_with_otp')
def login_with_otp():
    return render_template('login_with_otp.html', show_otp_form=False)

@app.route('/send_otp', methods=['POST'])
def send_otp():
    phone_number = request.form.get('phone_number')
    if not phone_number or len(phone_number) != 10:
        flash('Please enter a valid 10-digit phone number', 'error')
        return redirect(url_for('login_with_otp'))

    # Generate 6-digit OTP
    otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    expires_at = datetime.now() + timedelta(minutes=10)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Store OTP in database
        cursor.execute(
            "INSERT INTO otp_verifications (phone_number, otp, expires_at) VALUES (%s, %s, %s)",
            (phone_number, otp, expires_at)
        )
        conn.commit()
        cursor.close()

    # For testing, show OTP (in production, send via SMS)
    flash(f'Your OTP is: {otp}', 'info')
    return render_template('login_with_otp.html', show_otp_form=True)

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    phone_number = request.form.get('phone_number')
    otp = request.form.get('otp')

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        # Verify OTP
        cursor.execute(
            """SELECT * FROM otp_verifications 
               WHERE phone_number = %s 
               AND otp = %s 
               AND expires_at > NOW() 
               AND is_used = FALSE
               ORDER BY created_at DESC LIMIT 1""",
            (phone_number, otp)
        )
        verification = cursor.fetchone()

        if verification:
            # Mark OTP as used
            cursor.execute(
                "UPDATE otp_verifications SET is_used = TRUE WHERE id = %s",
                (verification['id'],)
            )
            
            # Get user details
            cursor.execute("SELECT * FROM users WHERE phone_number = %s", (phone_number,))
            user = cursor.fetchone()
            
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                conn.commit()
                cursor.close()
                return redirect(url_for('dashboard'))
            else:
                flash('User not found with this phone number', 'error')
        else:
            flash('Invalid or expired OTP', 'error')

        cursor.close()
    return redirect(url_for('login_with_otp'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('home'))

    return render_template('dashboard.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            # Get form data
            form_data = {
                'full_name': request.form.get('full_name'),
                'phone_number': request.form.get('phone_number'),
                'username': request.form.get('username'),
                'gender': request.form.get('gender', 'Not specified'),
                'bio': request.form.get('bio', ''),
                'location': request.form.get('location', '')
            }

            # Validate form data
            if not all([form_data['full_name'], form_data['phone_number'], form_data['username'],
                       request.form.get('password'), request.form.get('confirm_password')]):
                flash("Full Name, Phone Number, Username and Password are mandatory!", "danger")
                return render_template('register.html', avatars=AVATARS, form_data=form_data)

            if not form_data['phone_number'].isdigit() or len(form_data['phone_number']) != 10:
                flash("Phone number should be exactly 10 digits!", "danger")
                return render_template('register.html', avatars=AVATARS, form_data=form_data)

            # Database connection with context management
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)

                try:
                    # Check duplicate phone
                    cursor.execute("SELECT * FROM users WHERE phone_number = %s", (form_data['phone_number'],))
                    if cursor.fetchone():
                        flash("This phone number is already registered!", "danger")
                        return render_template('register.html', avatars=AVATARS, form_data=form_data)

                    # Check duplicate username
                    cursor.execute("SELECT * FROM users WHERE username = %s", (form_data['username'],))
                    if cursor.fetchone():
                        flash("This username is already taken!", "danger")
                        return render_template('register.html', avatars=AVATARS, form_data=form_data)

                    if request.form.get('password') != request.form.get('confirm_password'):
                        flash("Passwords do not match!", "danger")
                        return render_template('register.html', avatars=AVATARS, form_data=form_data)

                    # Hash password
                    hashed_password = bcrypt.hashpw(request.form.get('password').encode('utf-8'), 
                                                 bcrypt.gensalt()).decode('utf-8')

                    # Handle profile picture
                    profile_picture = "default_profile.png"
                    file = request.files.get('avatar_file')
                    avatar_choice = request.form.get('avatar_choice')

                    if file and file.filename:
                        if allowed_file(file.filename):
                            try:
                                filename = secure_filename(file.filename)
                                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                                file.save(file_path)
                                profile_picture = filename
                            except Exception as e:
                                app.logger.error(f"File upload error: {str(e)}")
                                flash("Error uploading file. Using default profile picture.", "warning")
                        else:
                            flash("Invalid file type. Using default profile picture.", "warning")
                    elif avatar_choice in AVATARS:
                        profile_picture = avatar_choice

                    # Insert user
                    cursor.execute(
                        """INSERT INTO users 
                           (full_name, phone_number, username, password, gender, bio, location, profile_picture) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (form_data['full_name'], form_data['phone_number'], form_data['username'],
                         hashed_password, form_data['gender'], form_data['bio'], form_data['location'],
                         profile_picture)
                    )
                    conn.commit()
                    flash("Registration successful!", "success")
                    return redirect(url_for('home'))

                except Exception as e:
                    conn.rollback()
                    app.logger.error(f"Database error during registration: {str(e)}")
                    flash("An error occurred during registration. Please try again.", "danger")
                    return render_template('register.html', avatars=AVATARS, form_data=form_data)
                finally:
                    cursor.close()

        except Exception as e:
            app.logger.error(f"Registration error: {str(e)}\n{traceback.format_exc()}")
            flash("An unexpected error occurred. Please try again.", "danger")
            return render_template('register.html', avatars=AVATARS, form_data=form_data)

    return render_template('register.html', avatars=AVATARS, form_data={})

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('home'))

    user_id = session['user_id']
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT full_name, username, phone_number, gender, bio, location, profile_picture FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()

    return render_template('profile.html', user=user, avatars=AVATARS)

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('home'))

    user_id = session['user_id']
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        if request.method == 'POST':
            full_name = request.form.get('full_name')
            phone_number = request.form.get('phone_number')
            gender = request.form.get('gender')
            bio = request.form.get('bio')
            location = request.form.get('location')
            avatar_choice = request.form.get('avatar_choice')
            file = request.files.get('avatar_file')

            profile_picture = None
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile_picture = filename
            elif avatar_choice in AVATARS:
                profile_picture = avatar_choice

            update_query = """
                UPDATE users SET full_name = %s, phone_number = %s, gender = %s, bio = %s, location = %s
            """ + (", profile_picture = %s" if profile_picture else "") + " WHERE id = %s"

            data = [full_name, phone_number, gender, bio, location]
            if profile_picture:
                data.append(profile_picture)
            data.append(user_id)

            cursor.execute(update_query, tuple(data))
            conn.commit()
            cursor.close()

            flash("Profile updated successfully!", "success")
            return redirect(url_for('profile'))

        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()rip(),
scription', '').strip(),
    return render_template('edit_profile.html', user=user, avatars=AVATARS)ocation', '').strip(),
# Optional
@app.route('/post_job', methods=['GET', 'POST']) '').strip(),
def post_job():            'job_type': request.form.get('job_type', '').strip()
    if 'user_id' not in session:
        flash("You must be logged in to post a job.", "warning")
        return redirect(url_for('home'))
        app.logger.info(f"Received job post data: {form_data}")
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        location = request.form.get('location')
        salary = request.form.get('salary')
        phone_number = request.form.get('phone_number')t form_data['location']: missing_fields.append('Location')
        job_type = request.form.get('job_type')  # New field'phone_number']: missing_fields.append('Phone Number')
job_type']: missing_fields.append('Job Type')
        if not title or not description or not location or not phone_number or not job_type:
            flash("All fields except salary are required!", "danger")
            return redirect(url_for('post_job')) {', '.join(missing_fields)}", "danger")
            return render_template('post_job.html', job_titles=RURAL_JOB_TITLES, form_data=form_data)
        with get_db_connection() as conn:
            cursor = conn.cursor()        try:
            cursor.execute(            with get_db_connection() as conn:
                "INSERT INTO jobs (title, description, location, salary, phone_number, job_type, posted_by) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (title, description, location, salary, phone_number, job_type, session['user_id'])rsor.execute(
            )
            conn.commit()n, salary, phone_number, job_type, posted_by) 
            cursor.close()%s, %s)""",
escription'], form_data['location'],
        flash("Job posted successfully!", "success")ta['phone_number'], form_data['job_type'],
        return redirect(url_for('post_job'))

    return render_template('post_job.html', job_titles=RURAL_JOB_TITLES)
                flash("Job posted successfully!", "success")
or('search_jobs'))
@app.route('/search_jobs', methods=['GET', 'POST'])
def search_jobs():            app.logger.error(f"Error posting job: {str(e)}")
    filter_by = request.form.get('filter_by', '')An error occurred while posting the job", "danger")
    salary_min = request.form.get('salary_min', '')B_TITLES, form_data=form_data)
    salary_max = request.form.get('salary_max', '')
    sort_salary = request.form.get('sort_salary', '')render_template('post_job.html', job_titles=RURAL_JOB_TITLES)
    job_title = request.form.get('job_title', '')
    location = request.form.get('location', '')_jobs', methods=['GET', 'POST'])
    date_posted = request.form.get('date_posted', '')def search_jobs():
    job_type = request.form.get('job_type', '')'filter_by', '')
orm.get('salary_min', '')
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)salary', '')
rm.get('job_title', '')
        query = """
        SELECT jobs.*, users.full_name, users.profile_picture FROM jobsposted', '')
        JOIN users ON jobs.posted_by = users.id
        """
        filters = []:
        params = []

        if filter_by == 'salary':
            if salary_min:cture FROM jobs
                filters.append("CAST(jobs.salary AS UNSIGNED) >= %s")
                params.append(salary_min)
            if salary_max:
                filters.append("CAST(jobs.salary AS UNSIGNED) <= %s")
                params.append(salary_max)
        elif filter_by == 'job_title' and job_title:        if filter_by == 'salary':
            filters.append("jobs.title = %s")ry_min:
            params.append(job_title)SIGNED) >= %s")
        elif filter_by == 'location' and location:                params.append(salary_min)
            filters.append("jobs.location LIKE %s")
            params.append(f"%{location}%")")
        elif filter_by == 'date_posted' and date_posted:
            filters.append("DATEDIFF(NOW(), jobs.created_at) <= %s")
            params.append(date_posted)            filters.append("jobs.title = %s")
        elif filter_by == 'job_type' and job_type:
            filters.append("jobs.job_type = %s")ion' and location:
            params.append(job_type)            filters.append("jobs.location LIKE %s")
cation}%")
        if filters:and date_posted:
            query += " WHERE " + " AND ".join(filters)

        if sort_salary == 'high_to_low':filter_by == 'job_type' and job_type:
            query += " ORDER BY CAST(jobs.salary AS UNSIGNED) DESC""jobs.job_type = %s")
        elif sort_salary == 'low_to_high':            params.append(job_type)
            query += " ORDER BY CAST(jobs.salary AS UNSIGNED) ASC"
        if filters:
        cursor.execute(query, tuple(params))E " + " AND ".join(filters)
        jobs = cursor.fetchall()
lary == 'high_to_low':
        if 'user_id' in session:(jobs.salary AS UNSIGNED) DESC"
            user_id = session['user_id']'low_to_high':
            cursor.execute("SELECT job_id FROM bookmarks WHERE user_id = %s", (user_id,))Y CAST(jobs.salary AS UNSIGNED) ASC"
            saved_jobs = [row['job_id'] for row in cursor.fetchall()]
        else:ple(params))
            saved_jobs = []ll()

        cursor.close()
ion['user_id']
    return render_template(ser_id = %s", (user_id,))
        "search_jobs.html",       saved_jobs = [row['job_id'] for row in cursor.fetchall()]
        jobs=jobs,        else:
        job_titles=RURAL_JOB_TITLES,
        filter_by=filter_by,
        salary_min=salary_min,
        salary_max=salary_max,
        sort_salary=sort_salary,
        job_title=job_title,        "search_jobs.html",
        location=location,
        date_posted=date_posted,
        job_type=job_type,
        saved_jobs=saved_jobs  # Pass saved_jobs to the template
    )

@app.route('/post_animal', methods=['GET', 'POST'])
def post_animal():
    if 'user_id' not in session:
        flash("You must be logged in to post an animal.", "warning")
        return redirect(url_for('home'))late

    if request.method == 'POST':
        category = request.form.get('animal_category')
        custom_animal = request.form.get('custom_animal', '')def post_animal():
        animal_name = custom_animal if category == 'custom' else category
        age = request.form.get('animal_age')")
        age = int(age) if age and age.strip() else None
        breed = request.form.get('animal_breed')
        breed = breed if breed and breed.strip() else NoneST':
        weight = request.form.get('animal_weight')orm.get('animal_category')
        price = request.form.get('animal_cost')stom_animal', '')
        description = request.form.get('animal_description')' else category
        location = request.form.get('animal_location')
        contact_number = request.form.get('contact_number')se None
        photos = request.files.getlist('animal_photos')        breed = request.form.get('animal_breed')
strip() else None
        if not all([animal_name, weight, price, location, contact_number]):'animal_weight')
            flash("Please fill in all required fields!", "danger")m.get('animal_cost')
            return redirect(url_for('post_animal'))

        photo_filenames = []
        for photo in photos:
            if allowed_file(photo.filename):
                filename = secure_filename(photo.filename)t all([animal_name, weight, price, location, contact_number]):
                photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename)) fill in all required fields!", "danger")
                photo_filenames.append(filename)t(url_for('post_animal'))

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(            if allowed_file(photo.filename):
                """INSERT INTO animals (category, age, breed, weight, cost, description, to.filename)
                   location, contact_number, photos, posted_by)                photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (animal_name, age, breed, weight, price, description, location, 
                 contact_number, ','.join(photo_filenames), session.get('user_id'))
            )
            conn.commit()
            cursor.close()ge, breed, weight, cost, description, 
otos, posted_by)
        flash("Animal posted successfully!", "success")%s, %s, %s, %s, %s)""",
        return redirect(url_for('search_animals'))                (animal_name, age, breed, weight, price, description, location, 
join(photo_filenames), session.get('user_id'))
    return render_template('post_animal.html')
mmit()
@app.route('/search_animals', methods=['GET', 'POST'])
def search_animals():
    filter_by = request.form.get('filter_by', '')ess")
    price_min = request.form.get('price_min', '')urn redirect(url_for('search_animals'))
    price_max = request.form.get('price_max', '')
    sort_price = request.form.get('sort_price', '')emplate('post_animal.html')
    category = request.form.get('category', '')
    location = request.form.get('location', '')thods=['GET', 'POST'])

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)min', '')
        query = """orm.get('price_max', '')
        SELECT animals.*, users.full_name, users.profile_picture 
        FROM animalsy', '')
        JOIN users ON animals.posted_by = users.id
        """
        filters = []n:
        params = []

        if filter_by == 'price': users.profile_picture 
            if price_min:        FROM animals
                filters.append("animals.cost >= %s")ON animals.posted_by = users.id
                params.append(price_min)
            if price_max:        filters = []
                filters.append("animals.cost <= %s")
                params.append(price_max)
        elif filter_by == 'category' and category:
            filters.append("animals.category = %s")
            params.append(category)                filters.append("animals.cost >= %s")
        elif filter_by == 'location' and location:
            filters.append("animals.location LIKE %s")
            params.append(f"%{location}%")                filters.append("animals.cost <= %s")
ice_max)
        if filters:
            query += " WHERE " + " AND ".join(filters)%s")

        if sort_price == 'high_to_low':filter_by == 'location' and location:
            query += " ORDER BY animals.cost DESC"imals.location LIKE %s")
        elif sort_price == 'low_to_high':            params.append(f"%{location}%")
            query += " ORDER BY animals.cost ASC"
        if filters:
        cursor.execute(query, tuple(params))ers)
        animals = cursor.fetchall()

        if 'user_id' in session:DESC"
            cursor.execute("SELECT animal_id FROM animal_bookmarks WHERE user_id = %s", 
                         (session['user_id'],))C"
            saved_animals = [row['animal_id'] for row in cursor.fetchall()]
        else:)
            saved_animals = []

        cursor.close()
"SELECT animal_id FROM animal_bookmarks WHERE user_id = %s", 
    return render_template('search_animals.html', n['user_id'],))
                         animals=animals,
                         filter_by=filter_by,        else:
                         price_min=price_min,
                         price_max=price_max,
                         sort_price=sort_price,
                         category=category,
                         location=location,
                         saved_animals=saved_animals)als,

@app.route('/save_animal/<int:animal_id>', methods=['POST'])             price_min=price_min,
def save_animal(animal_id):ice_max=price_max,
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please log in first'})tegory,
            location=location,
    user_id = session['user_id']aved_animals)
    try:
        with get_db_connection() as conn:/<int:animal_id>', methods=['POST'])
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM animals WHERE id = %s", (animal_id,))
            if not cursor.fetchone():, 'message': 'Please log in first'})
                return jsonify({'success': False, 'message': 'Animal not found'})
            d']
            cursor.execute(
                "SELECT id FROM animal_bookmarks WHERE user_id = %s AND animal_id = %s",) as conn:
                (user_id, animal_id)
            )OM animals WHERE id = %s", (animal_id,))
            existing = cursor.fetchone()t cursor.fetchone():
            fy({'success': False, 'message': 'Animal not found'})
            if existing:
                cursor.execute(e(
                    "DELETE FROM animal_bookmarks WHERE user_id = %s AND animal_id = %s",d = %s AND animal_id = %s",
                    (user_id, animal_id)    (user_id, animal_id)
                )
                saved = False
            else:
                cursor.execute(            if existing:
                    "INSERT INTO animal_bookmarks (user_id, animal_id) VALUES (%s, %s)",te(
                    (user_id, animal_id)"DELETE FROM animal_bookmarks WHERE user_id = %s AND animal_id = %s",
                )imal_id)
                saved = True
                
            conn.commit()            else:
            return jsonify({'success': True, 'saved': saved})
            arks (user_id, animal_id) VALUES (%s, %s)",
    except Exception as e:id, animal_id)
        app.logger.error(f"Error saving animal: {str(e)}")
        return jsonify({'success': False, 'message': 'Database error occurred'})

@app.route('/saved_animals')
def saved_animals():saved})
    if 'user_id' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('home'))ving animal: {str(e)}")
 'message': 'Database error occurred'})
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)@app.route('/saved_animals')
        cursor.execute("""
            SELECT animals.*, animal_bookmarks.created_at AS saved_at,     if 'user_id' not in session:
                   users.full_name, users.profile_picture
            FROM animal_bookmarkst(url_for('home'))
            JOIN animals ON animal_bookmarks.animal_id = animals.id
            JOIN users ON animals.posted_by = users.id
            WHERE animal_bookmarks.user_id = %scursor = conn.cursor(dictionary=True)
            ORDER BY animal_bookmarks.created_at DESC
        """, (session['user_id'],))eated_at AS saved_at, 
        saved_animals = cursor.fetchall()
        cursor.close()
JOIN animals ON animal_bookmarks.animal_id = animals.id
    return render_template('saved_animals.html', saved_animals=saved_animals)rs ON animals.posted_by = users.id
r_id = %s
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':imals = cursor.fetchall()
        login_id = request.form.get('login_id')  # Can be username or phone
        
        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s OR phone_number = %s", (login_id, login_id))ot_password', methods=['GET', 'POST'])
            user = cursor.fetchone()
            ethod == 'POST':
            if user:id = request.form.get('login_id')  # Can be username or phone
                # Generate reset token
                reset_token = secrets.token_urlsafe(32)
                expires_at = datetime.now() + timedelta(hours=1)cursor = conn.cursor(dictionary=True)
                umber = %s", (login_id, login_id))
                # Store reset token in databasefetchone()
                cursor.execute(    
                    "INSERT INTO password_resets (user_id, token, expires_at) VALUES (%s, %s, %s)",
                    (user['id'], reset_token, expires_at)                # Generate reset token
                )
                conn.commit() = datetime.now() + timedelta(hours=1)
                
              
                flash(f"Reset token: {reset_token}", "info")
                return redirect(url_for('reset_password', token=reset_token))            "INSERT INTO password_resets (user_id, token, expires_at) VALUES (%s, %s, %s)",
            _at)
            flash("No account found with that username/phone number", "error")
            cursor.close()
                
    return render_template('forgot_password.html')
, "info")
@app.route('/reset_password/<token>', methods=['GET', 'POST'])token))
def reset_password(token):    
    if request.method == 'POST':that username/phone number", "error")
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        )
        if not new_password or len(new_password) < 6:
            flash("Password must be at least 6 characters long", "error")ds=['GET', 'POST'])
            return render_template('reset_password.html', token=token)
        
        if new_password != confirm_password:
            flash("Passwords don't match", "error") = request.form.get('confirm_password')
            return render_template('reset_password.html', token=token)
        w_password) < 6:
        with get_db_connection() as conn:flash("Password must be at least 6 characters long", "error")
            cursor = conn.cursor(dictionary=True)nder_template('reset_password.html', token=token)
            
            # Get reset record and check if valid
            cursor.execute(n't match", "error")
                """SELECT pr.*, u.username en)
                   FROM password_resets pr
                   JOIN users u ON u.id = pr.user_id db_connection() as conn:
                   WHERE pr.token = %s AND pr.expires_at > NOW() AND pr.used = FALSE""",tionary=True)
                (token,)
            )d and check if valid
            reset = cursor.fetchone()or.execute(
            
            if reset:
                # Update password  JOIN users u ON u.id = pr.user_id 
                hashed_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()) AND pr.used = FALSE""",
                cursor.execute(
                    "UPDATE users SET password = %s WHERE id = %s",
                    (hashed_password, reset['user_id'])            reset = cursor.fetchone()
                )
                # Mark token as used
                cursor.execute("UPDATE password_resets SET used = TRUE WHERE id = %s", (reset['id'],))                # Update password
                conn.commit()d_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt())
                   cursor.execute(
                flash(f"Password reset successful! You can now login with your new password", "success") "UPDATE users SET password = %s WHERE id = %s",
                return redirect(url_for('login'))user_id'])
            else:
                flash("Invalid or expired reset token", "error")                # Mark token as used
                cursor.close() SET used = TRUE WHERE id = %s", (reset['id'],))
                return redirect(url_for('forgot_password'))commit()

    # GET request - show reset form        ur new password", "success")
    return render_template('reset_password.html', token=token)                return redirect(url_for('login'))

@app.route('/logout')        flash("Invalid or expired reset token", "error")
def logout():
    session.clear()l_for('forgot_password'))
    flash("Logged out successfully!", "info")
    return redirect(url_for('home'))    

@app.route('/save_job/<int:job_id>', methods=['POST'])
def save_job(job_id):
    if 'user_id' not in session::
        return jsonify({'success': False, 'message': 'Please log in first'})
ssfully!", "info")
    user_id = session['user_id']
    try:
        with get_db_connection() as conn:save_job/<int:job_id>', methods=['POST'])
            cursor = conn.cursor()
            _id' not in session:
            # Check if job exists first'success': False, 'message': 'Please log in first'})
            cursor.execute("SELECT id FROM jobs WHERE id = %s", (job_id,))
            if not cursor.fetchone():]
                return jsonify({'success': False, 'message': 'Job not found'})
            onn:
            # Check if already bookmarkedr = conn.cursor()
            cursor.execute(
                "SELECT id FROM bookmarks WHERE user_id = %s AND job_id = %s", ck if job exists first
                (user_id, job_id)LECT id FROM jobs WHERE id = %s", (job_id,))
            )one():
            existing = cursor.fetchone()
            
            if existing:ck if already bookmarked
                # Remove bookmark
                cursor.execute("SELECT id FROM bookmarks WHERE user_id = %s AND job_id = %s", 
                    "DELETE FROM bookmarks WHERE user_id = %s AND job_id = %s", job_id)
                    (user_id, job_id)
                )existing = cursor.fetchone()
                saved = False
            else:
                # Add bookmark
                cursor.execute(                cursor.execute(
                    "INSERT INTO bookmarks (user_id, job_id) VALUES (%s, %s)", WHERE user_id = %s AND job_id = %s",
                    (user_id, job_id)d, job_id)
                )
                saved = True
                    else:
            conn.commit()
            return jsonify({'success': True, 'saved': saved})
            TO bookmarks (user_id, job_id) VALUES (%s, %s)",
    except Exception as e:
        app.logger.error(f"Error saving job: {str(e)}")
        return jsonify({'success': False, 'message': 'Database error occurred'})

@app.route('/get_job_status/<int:job_id>')    conn.commit()
def get_job_status(job_id): saved})
    if 'user_id' not in session:            
        return jsonify({'success': False, 'message': 'Please log in first', 'saved': False})
        r.error(f"Error saving job: {str(e)}")
    user_id = session['user_id']': False, 'message': 'Database error occurred'})
    with get_db_connection() as conn:
        cursor = conn.cursor()')
        cursor.execute("SELECT * FROM bookmarks WHERE user_id = %s AND job_id = %s", def get_job_status(job_id):
                      (user_id, job_id))
        saved = cursor.fetchone() is not Nonelse, 'message': 'Please log in first', 'saved': False})
        cursor.close()
            user_id = session['user_id']
    return jsonify({'success': True, 'saved': saved})() as conn:
or()
@app.route('/saved_jobs', methods=['GET'])
def saved_jobs():r_id, job_id))
    if 'user_id' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('home'))
saved})
    user_id = session['user_id']
    with get_db_connection() as conn:T'])
        cursor = conn.cursor(dictionary=True)
    if 'user_id' not in session:
        # Fetch saved jobs
        cursor.execute("""        return redirect(url_for('home'))
            SELECT jobs.*, bookmarks.created_at AS saved_at, users.full_name, users.profile_picture
            FROM bookmarkson['user_id']
            JOIN jobs ON bookmarks.job_id = jobs.id get_db_connection() as conn:
            JOIN users ON jobs.posted_by = users.idonary=True)
            WHERE bookmarks.user_id = %s
            ORDER BY bookmarks.created_at DESC
        """, (user_id,))
        saved_jobs = cursor.fetchall()okmarks.created_at AS saved_at, users.full_name, users.profile_picture
        cursor.close()

    return render_template('saved_jobs.html', saved_jobs=saved_jobs)jobs.posted_by = users.id

@app.route('/health')
def health_check():        """, (user_id,))
    try:.fetchall()
        # Test database connectione()
        with get_db_connection() as conn:
            cursor = conn.cursor()ml', saved_jobs=saved_jobs)
            cursor.execute('SELECT 1')
            cursor.fetchone()
            cursor.close()
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:nnection
        app.logger.error(f"Health check failed: {str(e)}")
        return jsonify({"status": "unhealthy", "database": "disconnected", "error": str(e)}), 500cursor()

@app.route('/drop_indexes')            cursor.fetchone()
def drop_indexes():close()
    try:onify({"status": "healthy", "database": "connected"}), 200
        with get_db_connection() as conn:
            cursor = conn.cursor()(f"Health check failed: {str(e)}")
            cursor.execute("DROP INDEX idx_animal_search ON animals") 500
            cursor.execute("DROP INDEX idx_animal_created ON animals")
            conn.commit()
            cursor.close()op_indexes():
        return "Indexes dropped successfully"
    except Exception as e:n:
        return f"Error dropping indexes: {str(e)}"
x_animal_search ON animals")
# Configure logging            cursor.execute("DROP INDEX idx_animal_created ON animals")
if not app.debug:
    if not os.path.exists('logs'):            cursor.close()
        os.mkdir('logs')s dropped successfully"
    file_handler = RotatingFileHandler('logs/rural_jobs.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)ot os.path.exists('logs'):
    app.logger.setLevel(logging.INFO)
    app.logger.info('Rural Jobs startup')tatingFileHandler('logs/rural_jobs.log', maxBytes=10240, backupCount=10)
etFormatter(logging.Formatter(
app.jinja_env.filters['escapejs'] = escapeelname)s: %(message)s [in %(pathname)s:%(lineno)d]'

@app.errorhandler(404)file_handler.setLevel(logging.INFO)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):apejs'] = escape
    try:
        db = get_db_connection()












    app.run(host='0.0.0.0', port=port)    port = int(os.environ.get("PORT", 5000))if __name__ == '__main__':    return render_template('errors/500.html'), 500    app.logger.error(traceback.format_exc())    app.logger.error('Server Error: %s', str(error))            app.logger.error(f"Error handling 500 error: {str(e)}")    except Exception as e:        db.close()        db.rollback()def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    try:
        db = get_db_connection()
        db.rollback()
        db.close()
    except Exception as e:
        app.logger.error(f"Error handling 500 error: {str(e)}")
    
    app.logger.error('Server Error: %s', str(error))
    app.logger.error(traceback.format_exc())
    return render_template('errors/500.html'), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)