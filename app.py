import os
import json
import random
from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify
import psycopg2
import psycopg2.extras
import bcrypt
from werkzeug.utils import secure_filename
import secrets
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
import traceback
import time
import socket
from contextlib import contextmanager
from markupsafe import escape

load_dotenv()

app = Flask(__name__)
app.config['DEBUG'] = True 

app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_secret_key')

UPLOAD_FOLDER = 'static/uploads/'
AVATAR_FOLDER = 'static/avatars/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

AVATARS = [
    "female1.jpg", "female2.jpg", "female3.jpg", "female4.jpg",
    "male1.jpg", "male2.jpg", "male3.jpg", "male4.jpg"
]

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
        db_config = {
            'host': os.getenv('DB_HOST'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'dbname': os.getenv('DB_NAME'),
            'port': int(os.getenv('DB_PORT')),
        }
        app.logger.info(f"Attempting database connection to {db_config['host']}:{db_config['port']} as {db_config['user']}")
        conn = psycopg2.connect(**db_config)
        yield conn
    except Exception as e:
        app.logger.error(f"Database connection failed: {str(e)}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
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
            try:
                return text.format(*args, **kwargs)
            except Exception:
                return text  # fallback if formatting fails
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

            app.logger.info(f"Login attempt for: {login_id}")

            with get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute("SELECT * FROM users WHERE username = %s OR phone_number = %s", 
                             (login_id, login_id))
                user = cursor.fetchone()
                cursor.close()

                if user:
                    app.logger.info(f"User found for login_id: {login_id}, user_id: {user['id']}")
                    try:
                        if bcrypt.checkpw(password.encode(), user['password'].encode()):
                            session['user_id'] = user['id']
                            session['username'] = user['username']
                            flash("Login successful!", "success")
                            return redirect(url_for('dashboard'))  # Redirect to dashboard
                        else:
                            app.logger.warning(f"Password mismatch for user_id: {user['id']}")
                            flash("Incorrect Password or Username/Phone", "danger")
                            return redirect(url_for('home'))  # Redirect to login page
                    except Exception as e:
                        app.logger.error(f"Password hash error for user_id: {user['id']}: {e}")
                        flash("Unable to process login. Please try again.", "error")
                        return redirect(url_for('home'))
                else:
                    app.logger.warning(f"No user found for login_id: {login_id}")
                    flash("Incorrect Password or Username/Phone", "danger")
                    return redirect(url_for('home'))  # Redirect to login page

        except Exception as e:
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

    otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    expires_at = datetime.now() + timedelta(minutes=10)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO otp_verifications (phone_number, otp, expires_at) VALUES (%s, %s, %s)",
            (phone_number, otp, expires_at)
        )
        conn.commit()
        cursor.close()

    flash(f'Your OTP is: {otp}', 'info')
    return render_template('login_with_otp.html', show_otp_form=True)

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    phone_number = request.form.get('phone_number')
    otp = request.form.get('otp')

    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

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
            cursor.execute(
                "UPDATE otp_verifications SET is_used = TRUE WHERE id = %s",
                (verification['id'],)
            )
            
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
            form_data = {
                'full_name': request.form.get('full_name'),
                'phone_number': request.form.get('phone_number'),
                'username': request.form.get('username'),
                'gender': request.form.get('gender', 'Not specified'),
                'bio': request.form.get('bio', ''),
                'location': request.form.get('location', '')
            }

            if not all([form_data['full_name'], form_data['phone_number'], form_data['username'],
                       request.form.get('password'), request.form.get('confirm_password')]):
                flash("Full Name, Phone Number, Username and Password are mandatory!", "danger")
                return render_template('register.html', avatars=AVATARS, form_data=form_data)

            if not form_data['phone_number'].isdigit() or len(form_data['phone_number']) != 10:
                flash("Phone number should be exactly 10 digits!", "danger")
                return render_template('register.html', avatars=AVATARS, form_data=form_data)

            with get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

                try:
                    cursor.execute("SELECT * FROM users WHERE phone_number = %s", (form_data['phone_number'],))
                    if cursor.fetchone():
                        flash("This phone number is already registered!", "danger")
                        return render_template('register.html', avatars=AVATARS, form_data=form_data)

                    cursor.execute("SELECT * FROM users WHERE username = %s", (form_data['username'],))
                    if cursor.fetchone():
                        flash("This username is already taken!", "danger")
                        return render_template('register.html', avatars=AVATARS, form_data=form_data)

                    if request.form.get('password') != request.form.get('confirm_password'):
                        flash("Passwords do not match!", "danger")
                        return render_template('register.html', avatars=AVATARS, form_data=form_data)

                    hashed_password = bcrypt.hashpw(request.form.get('password').encode('utf-8'), 
                                                 bcrypt.gensalt()).decode('utf-8')

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

                    cursor.execute(
                        """INSERT INTO users 
                           (full_name, phone_number, username, password, gender, bio, location, profile_picture) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (form_data['full_name'], form_data['phone_number'], form_data['username'],
                         hashed_password, form_data['gender'], form_data['bio'], form_data['location'],
                         profile_picture)
                    )
                    conn.commit()
                    flash("Registration successful! Please log in.", "success")
                    return redirect(url_for('home'))  # Redirect to login page

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
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
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
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if request.method == 'POST':
            try:
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
                flash("Profile updated successfully!", "success")
                cursor.close()
                return redirect(url_for('profile'))
            except Exception as e:
                app.logger.error(f"Error updating profile: {str(e)}")
                flash("An error occurred while updating your profile. Please try again.", "danger")
                cursor.close()
                return redirect(url_for('edit_profile'))

        try:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                flash("User not found. Please contact support.", "danger")
                cursor.close()
                return redirect(url_for('dashboard'))
        except Exception as e:
            app.logger.error(f"Error fetching user data: {str(e)}")
            flash("An error occurred while fetching your profile. Please try again later.", "danger")
            cursor.close()
            return redirect(url_for('dashboard'))
        cursor.close()

    return render_template('edit_profile.html', user=user, avatars=AVATARS)

@app.route('/post_job', methods=['GET', 'POST'])
def post_job():
    if 'user_id' not in session:
        flash("You must be logged in to post a job.", "warning")
        return redirect(url_for('home')) 

    if request.method == 'POST':
        # Collect form data
        form_data = {
            'title': request.form.get('title', '').strip(),
            'description': request.form.get('description', '').strip(),
            'location': request.form.get('location', '').strip(),
            'salary': request.form.get('salary', '').strip(),  # Optional
            'phone_number': request.form.get('phone_number', '').strip(),
            'job_type': request.form.get('job_type', '').strip()
        }

        app.logger.info(f"Received job post data: {form_data}")

        missing_fields = [field for field in ['title', 'description', 'location', 'phone_number', 'job_type'] if not form_data[field]]
        if missing_fields:
            app.logger.error(f"Missing fields: {missing_fields}")
            flash(f"Missing required fields: {', '.join(missing_fields)}", "danger")
            return render_template('post_job.html', job_titles=RURAL_JOB_TITLES, form_data=form_data)

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """INSERT INTO jobs 
                       (title, description, location, salary, phone_number, job_type, posted_by) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (form_data['title'], form_data['description'], form_data['location'],
                     form_data['salary'], form_data['phone_number'], form_data['job_type'],
                     session['user_id'])
                )
                conn.commit()

                app.logger.info(f"Job posted successfully by user {session['user_id']}")
                flash("Job posted successfully!", "success")
                return redirect(url_for('post_job'))  
        except Exception as e:
            app.logger.error(f"Error posting job: {str(e)}")
            flash("An error occurred while posting the job. Please try again.", "danger")
            return render_template('post_job.html', job_titles=RURAL_JOB_TITLES, form_data=form_data)

    return render_template('post_job.html', job_titles=RURAL_JOB_TITLES)

@app.route('/search_jobs', methods=['GET', 'POST'])
def search_jobs():
    filter_by = request.form.get('filter_by', '')
    salary_min = request.form.get('salary_min', '')
    salary_max = request.form.get('salary_max', '')
    sort_salary = request.form.get('sort_salary', '')
    job_title = request.form.get('job_title', '')
    location = request.form.get('location', '')
    date_posted = request.form.get('date_posted', '')
    job_type = request.form.get('job_type', '')

    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = """
        SELECT jobs.*, users.full_name, users.profile_picture FROM jobs
        JOIN users ON jobs.posted_by = users.id
        """
        filters = []
        params = []

        if filter_by == 'salary':
            if salary_min:
                filters.append("CAST(jobs.salary AS UNSIGNED) >= %s")
                params.append(salary_min)
            if salary_max:
                filters.append("CAST(jobs.salary AS UNSIGNED) <= %s")
                params.append(salary_max)
        elif filter_by == 'job_title' and job_title:
            filters.append("jobs.title = %s")
            params.append(job_title)
        elif filter_by == 'location' and location:
            filters.append("jobs.location LIKE %s")
            params.append(f"%{location}%")
        elif filter_by == 'date_posted' and date_posted:
            filters.append("DATEDIFF(NOW(), jobs.created_at) <= %s")
            params.append(date_posted)
        elif filter_by == 'job_type' and job_type:
            filters.append("jobs.job_type = %s")
            params.append(job_type)

        if filters:
            query += " WHERE " + " AND ".join(filters)

        if sort_salary == 'high_to_low':
            query += " ORDER BY CAST(jobs.salary AS UNSIGNED) DESC"
        elif sort_salary == 'low_to_high':
            query += " ORDER BY CAST(jobs.salary AS UNSIGNED) ASC"

        cursor.execute(query, tuple(params))
        jobs = cursor.fetchall()

        if 'user_id' in session:
            user_id = session['user_id']
            cursor.execute("SELECT job_id FROM bookmarks WHERE user_id = %s", (user_id,))
            saved_jobs = [row['job_id'] for row in cursor.fetchall()]
        else:
            saved_jobs = []

        cursor.close()

    return render_template(
        "search_jobs.html",
        jobs=jobs,
        job_titles=RURAL_JOB_TITLES,
        filter_by=filter_by,
        salary_min=salary_min,
        salary_max=salary_max,
        sort_salary=sort_salary,
        job_title=job_title,
        location=location,
        date_posted=date_posted,
        job_type=job_type,
        saved_jobs=saved_jobs  
    )

@app.route('/post_animal', methods=['GET', 'POST'])
def post_animal():
    if 'user_id' not in session:
        flash("You must be logged in to post an animal.", "warning")
        return redirect(url_for('home')) 

    if request.method == 'POST':
        category = request.form.get('animal_category')
        custom_animal = request.form.get('custom_animal', '')
        animal_name = custom_animal if category == 'custom' else category
        age = request.form.get('animal_age')
        age = int(age) if age and age.strip() else None
        breed = request.form.get('animal_breed')
        breed = breed if breed and breed.strip() else None
        weight = request.form.get('animal_weight')
        price = request.form.get('animal_cost')
        description = request.form.get('animal_description')
        location = request.form.get('animal_location')
        contact_number = request.form.get('contact_number')
        photos = request.files.getlist('animal_photos')

        # Limit to 4 files and skip empty files
        photo_filenames = []
        for photo in photos[:4]:
            if photo and allowed_file(photo.filename):
                filename = secure_filename(photo.filename)
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                # Ensure unique filename
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(save_path):
                    filename = f"{base}_{counter}{ext}"
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    counter += 1
                photo.save(save_path)
                photo_filenames.append(filename)

        # Ensure numeric fields are correct for PostgreSQL
        try:
            weight = float(weight)
            price = float(price)
        except Exception:
            flash("Weight and Price must be numbers.", "danger")
            return render_template('post_animal.html')

        if not all([animal_name, weight, price, location, contact_number]):
            flash("Please fill in all required fields!", "danger")
            return render_template('post_animal.html')  

        if not photo_filenames:
            flash("Please upload at least one valid image.", "danger")
            return render_template('post_animal.html')

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO animals (category, age, breed, weight, cost, description, 
                       location, contact_number, photos, posted_by)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (animal_name, age, breed, weight, price, description, location, 
                     contact_number, ','.join(photo_filenames), session.get('user_id'))
                )
                conn.commit()
                cursor.close()

            flash("Animal posted successfully!", "success")
            return redirect(url_for('post_animal'))  

        except Exception as e:
            app.logger.error(f"Error posting animal: {str(e)}")
            flash("An error occurred while posting the animal. Please try again.", "danger")
            return render_template('post_animal.html')

    return render_template('post_animal.html')

@app.route('/search_animals', methods=['GET', 'POST'])
def search_animals():
    filter_by = request.form.get('filter_by', '')
    price_min = request.form.get('price_min', '')
    price_max = request.form.get('price_max', '')
    sort_price = request.form.get('sort_price', '')
    category = request.form.get('category', '')
    location = request.form.get('location', '')

    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        query = """
        SELECT animals.*, users.full_name, users.profile_picture 
        FROM animals
        JOIN users ON animals.posted_by = users.id
        """
        filters = []
        params = []

        if filter_by == 'price':
            if price_min:
                filters.append("animals.cost >= %s")
                params.append(price_min)
            if price_max:
                filters.append("animals.cost <= %s")
                params.append(price_max)
        elif filter_by == 'category' and category:
            filters.append("animals.category = %s")
            params.append(category)
        elif filter_by == 'location' and location:
            filters.append("animals.location LIKE %s")
            params.append(f"%{location}%")

        if filters:
            query += " WHERE " + " AND ".join(filters)

        if sort_price == 'high_to_low':
            query += " ORDER BY animals.cost DESC"
        elif sort_price == 'low_to_high':
            query += " ORDER BY animals.cost ASC"

        cursor.execute(query, tuple(params))
        animals = cursor.fetchall()

        if 'user_id' in session:
            cursor.execute("SELECT animal_id FROM animal_bookmarks WHERE user_id = %s", 
                         (session['user_id'],))
            saved_animals = [row['animal_id'] for row in cursor.fetchall()]
        else:
            saved_animals = []

        cursor.close()

    return render_template('search_animals.html', 
                         animals=animals,
                         filter_by=filter_by,
                         price_min=price_min,
                         price_max=price_max,
                         sort_price=sort_price,
                         category=category,
                         location=location,
                         saved_animals=saved_animals)

@app.route('/save_animal/<int:animal_id>', methods=['POST'])
def save_animal(animal_id):
    if 'user_id' not in session:
        flash("Please log in first.", "warning")
        return jsonify({'success': False, 'message': 'Please log in first'})  

    user_id = session['user_id']
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM animals WHERE id = %s", (animal_id,))
            if not cursor.fetchone():
                return jsonify({'success': False, 'message': 'Animal not found'})
            
            cursor.execute(
                "SELECT id FROM animal_bookmarks WHERE user_id = %s AND animal_id = %s",
                (user_id, animal_id)
            )
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute(
                    "DELETE FROM animal_bookmarks WHERE user_id = %s AND animal_id = %s",
                    (user_id, animal_id)
                )
                saved = False
            else:
                cursor.execute(
                    "INSERT INTO animal_bookmarks (user_id, animal_id) VALUES (%s, %s)",
                    (user_id, animal_id)
                )
                saved = True
                
            conn.commit()
            return jsonify({'success': True, 'saved': saved})
            
    except Exception as e:
        app.logger.error(f"Error saving animal: {str(e)}")
        return jsonify({'success': False, 'message': 'Database error occurred'})

@app.route('/saved_animals')
def saved_animals():
    if 'user_id' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('home'))

    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("""
            SELECT animals.*, animal_bookmarks.created_at AS saved_at, 
                   users.full_name, users.profile_picture
            FROM animal_bookmarks
            JOIN animals ON animal_bookmarks.animal_id = animals.id
            JOIN users ON animals.posted_by = users.id
            WHERE animal_bookmarks.user_id = %s
            ORDER BY animal_bookmarks.created_at DESC
        """, (session['user_id'],))
        saved_animals = cursor.fetchall()
        cursor.close()

    return render_template('saved_animals.html', saved_animals=saved_animals)

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        login_id = request.form.get('login_id')  
        
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("SELECT * FROM users WHERE username = %s OR phone_number = %s", (login_id, login_id))
            user = cursor.fetchone()
            
            if user:
                reset_token = secrets.token_urlsafe(32)
                expires_at = datetime.now() + timedelta(hours=1)
                
                cursor.execute(
                    "INSERT INTO password_resets (user_id, token, expires_at) VALUES (%s, %s, %s)",
                    (user['id'], reset_token, expires_at)
                )
                conn.commit()
                
                # Redirect to the reset password page with the token
                return redirect(url_for('reset_password', token=reset_token))
            
            flash("No account found with that username/phone number", "danger")
            cursor.close()
            return redirect(url_for('forgot_password')) 
        
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not new_password or len(new_password) < 6:
            flash("Password must be at least 6 characters long", "error")
            return render_template('reset_password.html', token=token)
        
        if new_password != confirm_password:
            flash("Passwords don't match", "error")
            return render_template('reset_password.html', token=token)
        
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            cursor.execute(
                """SELECT pr.*, u.username 
                   FROM password_resets pr
                   JOIN users u ON u.id = pr.user_id 
                   WHERE pr.token = %s AND pr.expires_at > NOW() AND pr.used = FALSE""",
                (token,)
            )
            reset = cursor.fetchone()
            
            if reset:
                # Ensure password is stored as utf-8 string, not bytes
                hashed_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode('utf-8')
                cursor.execute(
                    "UPDATE users SET password = %s WHERE id = %s",
                    (hashed_password, reset['user_id'])
                )
                cursor.execute("UPDATE password_resets SET used = TRUE WHERE id = %s", (reset['id'],))
                conn.commit()
                
                flash("Password reset successful! You can now login with your new password", "success")
                return redirect(url_for('home'))  
            else:
                flash("Invalid or expired reset token", "danger")
                cursor.close()
                return redirect(url_for('forgot_password'))  

    return render_template('reset_password.html', token=token)

@app.route('/logout')
def logout():
    flash("Logged out successfully!", "info")
    session.clear()
    return redirect(url_for('home'))  

@app.route('/save_job/<int:job_id>', methods=['POST'])
def save_job(job_id):
    if 'user_id' not in session:
        flash("Please log in first.", "warning")
        return jsonify({'success': False, 'message': 'Please log in first'})  

    user_id = session['user_id']
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM jobs WHERE id = %s", (job_id,))
            if not cursor.fetchone():
                return jsonify({'success': False, 'message': 'Job not found'})
            
            cursor.execute(
                "SELECT id FROM bookmarks WHERE user_id = %s AND job_id = %s", 
                (user_id, job_id)
            )
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute(
                    "DELETE FROM bookmarks WHERE user_id = %s AND job_id = %s",
                    (user_id, job_id)
                )
                saved = False
            else:
                cursor.execute(
                    "INSERT INTO bookmarks (user_id, job_id) VALUES (%s, %s)",
                    (user_id, job_id)
                )
                saved = True
                
            conn.commit()
            return jsonify({'success': True, 'saved': saved})
            
    except Exception as e:
        app.logger.error(f"Error saving job: {str(e)}")
        return jsonify({'success': False, 'message': 'Database error occurred'})

@app.route('/get_job_status/<int:job_id>')
def get_job_status(job_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please log in first', 'saved': False})
        
    user_id = session['user_id']
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bookmarks WHERE user_id = %s AND job_id = %s", 
                      (user_id, job_id))
        saved = cursor.fetchone() is not None
        cursor.close()
        
    return jsonify({'success': True, 'saved': saved})

@app.route('/saved_jobs', methods=['GET'])
def saved_jobs():
    if 'user_id' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('home'))

    user_id = session['user_id']
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT jobs.*, bookmarks.created_at AS saved_at, users.full_name, users.profile_picture
            FROM bookmarks
            JOIN jobs ON bookmarks.job_id = jobs.id
            JOIN users ON jobs.posted_by = users.id
            WHERE bookmarks.user_id = %s
            ORDER BY bookmarks.created_at DESC
        """, (user_id,))
        saved_jobs = cursor.fetchall()
        cursor.close()

    return render_template('saved_jobs.html', saved_jobs=saved_jobs)

@app.route('/health')
def health_check():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            cursor.fetchone()
            cursor.close()
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        app.logger.error(f"Health check failed: {str(e)}")
        return jsonify({"status": "unhealthy", "database": "disconnected", "error": str(e)}), 500

@app.route('/drop_indexes')
def drop_indexes():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DROP INDEX idx_animal_search ON animals")
            cursor.execute("DROP INDEX idx_animal_created ON animals")
            conn.commit()
            cursor.close()
        return "Indexes dropped successfully"
    except Exception as e:
        return f"Error dropping indexes: {str(e)}"

@app.route('/db_test')
def db_test():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            result = cursor.fetchone()
            cursor.close()
        return f"Database connected! Result: {result}"
    except Exception as e:
        return f"Database connection failed: {e}"

if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/rural_jobs.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Rural Jobs startup')

app.jinja_env.filters['escapejs'] = escape

@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error('Server Error: %s', str(error))
    app.logger.error(traceback.format_exc())
    return render_template('errors/500.html'), 500

@app.route('/delete_job/<int:job_id>', methods=['POST'])
def delete_job(job_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please log in first'}), 401
    user_id = session['user_id']
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT posted_by FROM jobs WHERE id = %s", (job_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({'success': False, 'message': 'Job not found'}), 404
            if row[0] != user_id:
                return jsonify({'success': False, 'message': 'Unauthorized'}), 403
            cursor.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
            conn.commit()
            cursor.close()
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Error deleting job: {str(e)}")
        return jsonify({'success': False, 'message': 'Error deleting job'}), 500

@app.route('/delete_animal/<int:animal_id>', methods=['POST'])
def delete_animal(animal_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please log in first'}), 401
    user_id = session['user_id']
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT posted_by FROM animals WHERE id = %s", (animal_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({'success': False, 'message': 'Animal not found'}), 404
            if row[0] != user_id:
                return jsonify({'success': False, 'message': 'Unauthorized'}), 403
            cursor.execute("DELETE FROM animals WHERE id = %s", (animal_id,))
            conn.commit()
            cursor.close()
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Error deleting animal: {str(e)}")
        return jsonify({'success': False, 'message': 'Error deleting animal'}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)