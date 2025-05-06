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
                    app.logger.info(f"User {user['username']} logged in successfully.")
                    flash("Login successful!", "success")
                    return redirect(url_for('dashboard'))
                else:
                    app.logger.warning(f"Failed login attempt for username/phone: {login_id}")
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
        cursor = conn.cursor(dictionary=True)

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
                cursor = conn.cursor(dictionary=True)

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
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT full_name, username, phone_number, gender, bio, location, profile_picture FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()

    return render_template('profile.html', user=user, avatars=AVATARS)

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():not logged in.")
    if 'user_id' not in session:arning")
        flash("Please log in first.", "warning")        return redirect(url_for('home'))
        return redirect(url_for('home'))

    user_id = session['user_id']page for user_id: {user_id}")
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True):

        if request.method == 'POST':
            full_name = request.form.get('full_name')
            phone_number = request.form.get('phone_number')
            gender = request.form.get('gender')name')
            bio = request.form.get('bio')')
            location = request.form.get('location')
            avatar_choice = request.form.get('avatar_choice')                bio = request.form.get('bio')
            file = request.files.get('avatar_file').form.get('location')
atar_choice')
            profile_picture = None
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))ile.filename):
                profile_picture = filenamefile.filename)
            elif avatar_choice in AVATARS:                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile_picture = avatar_choicecture = filename

            update_query = """
                UPDATE users SET full_name = %s, phone_number = %s, gender = %s, bio = %s, location = %s
            """ + (", profile_picture = %s" if profile_picture else "") + " WHERE id = %s"
s SET full_name = %s, phone_number = %s, gender = %s, bio = %s, location = %s
            data = [full_name, phone_number, gender, bio, location]%s" if profile_picture else "") + " WHERE id = %s"
            if profile_picture:
                data.append(profile_picture)                data = [full_name, phone_number, gender, bio, location]
            data.append(user_id)
append(profile_picture)
            cursor.execute(update_query, tuple(data))d(user_id)
            conn.commit()
            cursor.close()

            flash("Profile updated successfully!", "success")                app.logger.info(f"Profile updated successfully for user_id: {user_id}")
            return redirect(url_for('profile'))    flash("Profile updated successfully!", "success")

        try:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))on as e:
            user = cursor.fetchone()                app.logger.error(f"Error updating profile for user_id {user_id}: {str(e)}")
            cursor.close()n error occurred while updating your profile. Please try again.", "danger")

            if not user:
                app.logger.error(f"User with ID {user_id} not found in the database.")
                flash("User not found. Please contact support.", "danger")            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                return redirect(url_for('dashboard'))  # Redirect to dashboard if user not foundhone()

        except Exception as e:
            app.logger.error(f"Error fetching user data for ID {user_id}: {str(e)}")
            flash("An error occurred while fetching your profile. Please try again later.", "danger")                app.logger.error(f"User with ID {user_id} not found in the database.")
            return redirect(url_for('dashboard'))
                return redirect(url_for('dashboard'))  # Redirect to dashboard if user not found
    return render_template('edit_profile.html', user=user, avatars=AVATARS)
Exception as e:
@app.route('/post_job', methods=['GET', 'POST'])rror fetching user data for ID {user_id}: {str(e)}")
def post_job():. Please try again later.", "danger")
    if 'user_id' not in session:board'))
        flash("You must be logged in to post a job.", "warning")
        return redirect(url_for('home')) _profile.html', user=user, avatars=AVATARS)

    if request.method == 'POST':', methods=['GET', 'POST'])
        # Collect form data
        form_data = {
            'title': request.form.get('title', '').strip(),
            'description': request.form.get('description', '').strip(),
            'location': request.form.get('location', '').strip(),
            'salary': request.form.get('salary', '').strip(),  # Optional
            'phone_number': request.form.get('phone_number', '').strip(), Collect form data
            'job_type': request.form.get('job_type', '').strip()        form_data = {
        }
            'description': request.form.get('description', '').strip(),
        app.logger.info(f"Received job post data: {form_data}")
est.form.get('salary', '').strip(),  # Optional
        missing_fields = [field for field in ['title', 'description', 'location', 'phone_number', 'job_type'] if not form_data[field]]strip(),
        if missing_fields:
            app.logger.error(f"Missing fields: {missing_fields}")
            flash(f"Missing required fields: {', '.join(missing_fields)}", "danger")
            return render_template('post_job.html', job_titles=RURAL_JOB_TITLES, form_data=form_data)logger.info(f"Received job post data: {form_data}")

        try:eld in ['title', 'description', 'location', 'phone_number', 'job_type'] if not form_data[field]]
            with get_db_connection() as conn:        if missing_fields:
                cursor = conn.cursor()Missing fields: {missing_fields}")
lds: {', '.join(missing_fields)}", "danger")
                cursor.execute(ata)
                    """INSERT INTO jobs 
                       (title, description, location, salary, phone_number, job_type, posted_by) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (form_data['title'], form_data['description'], form_data['location'],
                     form_data['salary'], form_data['phone_number'], form_data['job_type'],
                     session['user_id'])e(
                )                    """INSERT INTO jobs 
                conn.commit()sted_by) 
",
                app.logger.info(f"Job posted successfully by user {session['user_id']}")scription'], form_data['location'],
                flash("Job posted successfully!", "success")['salary'], form_data['phone_number'], form_data['job_type'],
                return redirect(url_for('post_job'))  
        except Exception as e:
            app.logger.error(f"Error posting job: {str(e)}")
            flash("An error occurred while posting the job. Please try again.", "danger")
            return render_template('post_job.html', job_titles=RURAL_JOB_TITLES, form_data=form_data)on['user_id']}")
                flash("Job posted successfully!", "success")
    return render_template('post_job.html', job_titles=RURAL_JOB_TITLES))  
eption as e:
@app.route('/search_jobs', methods=['GET', 'POST']) {str(e)}")
def search_jobs():the job. Please try again.", "danger")
    filter_by = request.form.get('filter_by', '') job_titles=RURAL_JOB_TITLES, form_data=form_data)
    salary_min = request.form.get('salary_min', '')
    salary_max = request.form.get('salary_max', '')itles=RURAL_JOB_TITLES)
    sort_salary = request.form.get('sort_salary', '')
    job_title = request.form.get('job_title', '')
    location = request.form.get('location', '')
    date_posted = request.form.get('date_posted', '')    filter_by = request.form.get('filter_by', '')
    job_type = request.form.get('job_type', '')lary_min', '')
', '')
    with get_db_connection() as conn:    sort_salary = request.form.get('sort_salary', '')
        cursor = conn.cursor(dictionary=True)uest.form.get('job_title', '')

        query = """', '')
        SELECT jobs.*, users.full_name, users.profile_picture FROM jobse = request.form.get('job_type', '')
        JOIN users ON jobs.posted_by = users.id
        """nection() as conn:
        filters = []        cursor = conn.cursor(dictionary=True)
        params = []

        if filter_by == 'salary':bs
            if salary_min:ers.id
                filters.append("CAST(jobs.salary AS UNSIGNED) >= %s")
                params.append(salary_min)
            if salary_max:
                filters.append("CAST(jobs.salary AS UNSIGNED) <= %s")
                params.append(salary_max)
        elif filter_by == 'job_title' and job_title:
            filters.append("jobs.title = %s")S UNSIGNED) >= %s")
            params.append(job_title)
        elif filter_by == 'location' and location:
            filters.append("jobs.location LIKE %s")GNED) <= %s")
            params.append(f"%{location}%")
        elif filter_by == 'date_posted' and date_posted:and job_title:
            filters.append("DATEDIFF(NOW(), jobs.created_at) <= %s")
            params.append(date_posted)
        elif filter_by == 'job_type' and job_type:' and location:
            filters.append("jobs.job_type = %s")            filters.append("jobs.location LIKE %s")
            params.append(job_type)append(f"%{location}%")
d:
        if filters:            filters.append("DATEDIFF(NOW(), jobs.created_at) <= %s")
            query += " WHERE " + " AND ".join(filters)

        if sort_salary == 'high_to_low':= %s")
            query += " ORDER BY CAST(jobs.salary AS UNSIGNED) DESC"
        elif sort_salary == 'low_to_high':
            query += " ORDER BY CAST(jobs.salary AS UNSIGNED) ASC"
 " AND ".join(filters)
        cursor.execute(query, tuple(params))
        jobs = cursor.fetchall()to_low':
s.salary AS UNSIGNED) DESC"
        if 'user_id' in session:
            user_id = session['user_id']
            cursor.execute("SELECT job_id FROM bookmarks WHERE user_id = %s", (user_id,))
            saved_jobs = [row['job_id'] for row in cursor.fetchall()]y, tuple(params))
        else:        jobs = cursor.fetchall()
            saved_jobs = []
        if 'user_id' in session:
        cursor.close()on['user_id']
"SELECT job_id FROM bookmarks WHERE user_id = %s", (user_id,))
    return render_template(jobs = [row['job_id'] for row in cursor.fetchall()]
        "search_jobs.html",
        jobs=jobs,
        job_titles=RURAL_JOB_TITLES,
        filter_by=filter_by,
        salary_min=salary_min,
        salary_max=salary_max,
        sort_salary=sort_salary,,
        job_title=job_title,
        location=location,OB_TITLES,
        date_posted=date_posted,
        job_type=job_type,   salary_min=salary_min,
        saved_jobs=saved_jobs          salary_max=salary_max,
    )
job_title,
@app.route('/post_animal', methods=['GET', 'POST'])
def post_animal():
    if 'user_id' not in session:
        flash("You must be logged in to post an animal.", "warning")        saved_jobs=saved_jobs  
        return redirect(url_for('home')) 

    if request.method == 'POST':
        category = request.form.get('animal_category')
        custom_animal = request.form.get('custom_animal', '')
        animal_name = custom_animal if category == 'custom' else category", "warning")
        age = request.form.get('animal_age')
        age = int(age) if age and age.strip() else None
        breed = request.form.get('animal_breed')
        breed = breed if breed and breed.strip() else Noneegory')
        weight = request.form.get('animal_weight'))
        price = request.form.get('animal_cost')stom' else category
        description = request.form.get('animal_description')
        location = request.form.get('animal_location')
        contact_number = request.form.get('contact_number')        breed = request.form.get('animal_breed')
        photos = request.files.getlist('animal_photos')

        if not all([animal_name, weight, price, location, contact_number]):
            flash("Please fill in all required fields!", "danger")        description = request.form.get('animal_description')
            return render_template('post_animal.html')  orm.get('animal_location')
uest.form.get('contact_number')
        photo_filenames = []al_photos')
        for photo in photos:
            if allowed_file(photo.filename):
                filename = secure_filename(photo.filename)ields!", "danger")
                photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))            return render_template('post_animal.html')  
                photo_filenames.append(filename)

        try:
            with get_db_connection() as conn:to.filename):
                cursor = conn.cursor()
                cursor.execute(, filename))
                    """INSERT INTO animals (category, age, breed, weight, cost, description, 
                       location, contact_number, photos, posted_by)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (animal_name, age, breed, weight, price, description, location, get_db_connection() as conn:
                     contact_number, ','.join(photo_filenames), session.get('user_id')).cursor()
                )(
                conn.commit()                    """INSERT INTO animals (category, age, breed, weight, cost, description, 
                cursor.close()sted_by)
, %s, %s, %s, %s)""",
            flash("Animal posted successfully!", "success")                    (animal_name, age, breed, weight, price, description, location, 
            return redirect(url_for('post_animal'))  umber, ','.join(photo_filenames), session.get('user_id'))

        except Exception as e:
            app.logger.error(f"Error posting animal: {str(e)}")
            flash("An error occurred while posting the animal. Please try again.", "danger")
            return render_template('post_animal.html')", "success")
            return redirect(url_for('post_animal'))  
    return render_template('post_animal.html')
ion as e:
@app.route('/search_animals', methods=['GET', 'POST'])al: {str(e)}")
def search_animals():g the animal. Please try again.", "danger")
    filter_by = request.form.get('filter_by', '')tml')
    price_min = request.form.get('price_min', '')
    price_max = request.form.get('price_max', '')
    sort_price = request.form.get('sort_price', '')
    category = request.form.get('category', '')@app.route('/search_animals', methods=['GET', 'POST'])
    location = request.form.get('location', '')
 '')
    with get_db_connection() as conn:uest.form.get('price_min', '')
        cursor = conn.cursor(dictionary=True)
        query = """uest.form.get('sort_price', '')
        SELECT animals.*, users.full_name, users.profile_picture 
        FROM animalsn = request.form.get('location', '')
        JOIN users ON animals.posted_by = users.id
        """nection() as conn:
        filters = []        cursor = conn.cursor(dictionary=True)
        params = []
 users.full_name, users.profile_picture 
        if filter_by == 'price':
            if price_min:= users.id
                filters.append("animals.cost >= %s")
                params.append(price_min)
            if price_max:
                filters.append("animals.cost <= %s")
                params.append(price_max)
        elif filter_by == 'category' and category:
            filters.append("animals.category = %s")")
            params.append(category)
        elif filter_by == 'location' and location:
            filters.append("animals.location LIKE %s")                filters.append("animals.cost <= %s")
            params.append(f"%{location}%")ams.append(price_max)

        if filters:            filters.append("animals.category = %s")
            query += " WHERE " + " AND ".join(filters)

        if sort_price == 'high_to_low':ion LIKE %s")
            query += " ORDER BY animals.cost DESC"
        elif sort_price == 'low_to_high':
            query += " ORDER BY animals.cost ASC"
AND ".join(filters)
        cursor.execute(query, tuple(params))
        animals = cursor.fetchall()o_low':

        if 'user_id' in session:
            cursor.execute("SELECT animal_id FROM animal_bookmarks WHERE user_id = %s", 
                         (session['user_id'],))
            saved_animals = [row['animal_id'] for row in cursor.fetchall()]tuple(params))
        else:        animals = cursor.fetchall()
            saved_animals = []
        if 'user_id' in session:
        cursor.close()animal_bookmarks WHERE user_id = %s", 
d'],))
    return render_template('search_animals.html',  for row in cursor.fetchall()]
                         animals=animals,
                         filter_by=filter_by,
                         price_min=price_min,
                         price_max=price_max,
                         sort_price=sort_price,
                         category=category,
                         location=location,                         animals=animals,
                         saved_animals=saved_animals)
ice_min=price_min,
@app.route('/save_animal/<int:animal_id>', methods=['POST'])ax=price_max,
def save_animal(animal_id):
    if 'user_id' not in session:
        flash("Please log in first.", "warning")                         location=location,
        return jsonify({'success': False, 'message': 'Please log in first'})  nimals=saved_animals)

    user_id = session['user_id'], methods=['POST'])
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor() "warning")
            cursor.execute("SELECT id FROM animals WHERE id = %s", (animal_id,))
            if not cursor.fetchone():
                return jsonify({'success': False, 'message': 'Animal not found'})_id']
            
            cursor.execute(conn:
                "SELECT id FROM animal_bookmarks WHERE user_id = %s AND animal_id = %s",ursor = conn.cursor()
                (user_id, animal_id)OM animals WHERE id = %s", (animal_id,))
            )if not cursor.fetchone():
            existing = cursor.fetchone()sonify({'success': False, 'message': 'Animal not found'})
            
            if existing:
                cursor.execute(ookmarks WHERE user_id = %s AND animal_id = %s",
                    "DELETE FROM animal_bookmarks WHERE user_id = %s AND animal_id = %s",user_id, animal_id)
                    (user_id, animal_id)
                )ing = cursor.fetchone()
                saved = False
            else:
                cursor.execute(
                    "INSERT INTO animal_bookmarks (user_id, animal_id) VALUES (%s, %s)",   "DELETE FROM animal_bookmarks WHERE user_id = %s AND animal_id = %s",
                    (user_id, animal_id), animal_id)
                ))
                saved = Truealse
                
            conn.commit()    cursor.execute(
            return jsonify({'success': True, 'saved': saved})T INTO animal_bookmarks (user_id, animal_id) VALUES (%s, %s)",
            
    except Exception as e:
        app.logger.error(f"Error saving animal: {str(e)}")                saved = True
        return jsonify({'success': False, 'message': 'Database error occurred'})
mit()
@app.route('/saved_animals')cess': True, 'saved': saved})
def saved_animals():
    if 'user_id' not in session:
        flash("Please log in first.", "warning")        app.logger.error(f"Error saving animal: {str(e)}")
        return redirect(url_for('home'))lse, 'message': 'Database error occurred'})

    with get_db_connection() as conn:')
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT animals.*, animal_bookmarks.created_at AS saved_at, t.", "warning")
                   users.full_name, users.profile_picture
            FROM animal_bookmarks
            JOIN animals ON animal_bookmarks.animal_id = animals.id
            JOIN users ON animals.posted_by = users.id
            WHERE animal_bookmarks.user_id = %s
            ORDER BY animal_bookmarks.created_at DESCmarks.created_at AS saved_at, 
        """, (session['user_id'],))rs.full_name, users.profile_picture
        saved_animals = cursor.fetchall()            FROM animal_bookmarks
        cursor.close()
            JOIN users ON animals.posted_by = users.id
    return render_template('saved_animals.html', saved_animals=saved_animals)
nimal_bookmarks.created_at DESC
@app.route('/forgot_password', methods=['GET', 'POST']),))
def forgot_password():
    if request.method == 'POST':cursor.close()
        login_id = request.form.get('login_id')  
        saved_animals=saved_animals)
        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)ds=['GET', 'POST'])
            cursor.execute("SELECT * FROM users WHERE username = %s OR phone_number = %s", (login_id, login_id))assword():
            user = cursor.fetchone()d == 'POST':
            
            if user:
                reset_token = secrets.token_urlsafe(32)_db_connection() as conn:
                expires_at = datetime.now() + timedelta(hours=1)r(dictionary=True)
                d, login_id))
                cursor.execute(
                    "INSERT INTO password_resets (user_id, token, expires_at) VALUES (%s, %s, %s)",
                    (user['id'], reset_token, expires_at)
                )reset_token = secrets.token_urlsafe(32)
                conn.commit()  expires_at = datetime.now() + timedelta(hours=1)
                
              
                flash(f"Reset token: {reset_token}", "info")        "INSERT INTO password_resets (user_id, token, expires_at) VALUES (%s, %s, %s)",
                return redirect(url_for('home'))  
            
            flash("No account found with that username/phone number", "danger")
            cursor.close()        
            return redirect(url_for('forgot_password')) 
                        flash(f"Reset token: {reset_token}", "info")
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])und with that username/phone number", "danger")
def reset_password(token):
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not new_password or len(new_password) < 6:
            flash("Password must be at least 6 characters long", "error")t_password(token):
            return render_template('reset_password.html', token=token)
        rd')
        if new_password != confirm_password:
            flash("Passwords don't match", "error")
            return render_template('reset_password.html', token=token)ssword) < 6:
        aracters long", "error")
        with get_db_connection() as conn:return render_template('reset_password.html', token=token)
            cursor = conn.cursor(dictionary=True)
            :
            cursor.execute( "error")
                """SELECT pr.*, u.username ml', token=token)
                   FROM password_resets pr
                   JOIN users u ON u.id = pr.user_id ection() as conn:
                   WHERE pr.token = %s AND pr.expires_at > NOW() AND pr.used = FALSE""",ursor = conn.cursor(dictionary=True)
                (token,)
            )cursor.execute(
            reset = cursor.fetchone()LECT pr.*, u.username 
            
            if reset: ON u.id = pr.user_id 
                hashed_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt())D pr.used = FALSE""",
                cursor.execute(
                    "UPDATE users SET password = %s WHERE id = %s",
                    (hashed_password, reset['user_id'])
                )
                cursor.execute("UPDATE password_resets SET used = TRUE WHERE id = %s", (reset['id'],))eset:
                conn.commit()
                
                flash(f"Password reset successful! You can now login with your new password", "success")   "UPDATE users SET password = %s WHERE id = %s",
                return redirect(url_for('home'))  
            else:
                flash("Invalid or expired reset token", "danger")ed = TRUE WHERE id = %s", (reset['id'],))
                cursor.close()                conn.commit()
                return redirect(url_for('forgot_password'))  
                flash(f"Password reset successful! You can now login with your new password", "success")
    return render_template('reset_password.html', token=token)n redirect(url_for('home'))  
lse:
@app.route('/logout')sh("Invalid or expired reset token", "danger")
def logout():
    session.clear()r('forgot_password'))  
    flash("Logged out successfully!", "info")
    return redirect(url_for('home'))  n=token)

@app.route('/save_job/<int:job_id>', methods=['POST'])
def save_job(job_id):
    if 'user_id' not in session:
        flash("Please log in first.", "warning")    flash("Logged out successfully!", "info")
        return jsonify({'success': False, 'message': 'Please log in first'})  e'))  

    user_id = session['user_id']ods=['POST'])
    try:
        with get_db_connection() as conn:_id' not in session:
            cursor = conn.cursor()
            lse, 'message': 'Please log in first'})  
            cursor.execute("SELECT id FROM jobs WHERE id = %s", (job_id,))
            if not cursor.fetchone():= session['user_id']
                return jsonify({'success': False, 'message': 'Job not found'})
            
            cursor.execute()
                "SELECT id FROM bookmarks WHERE user_id = %s AND job_id = %s", 
                (user_id, job_id)OM jobs WHERE id = %s", (job_id,))
            )if not cursor.fetchone():
            existing = cursor.fetchone()sonify({'success': False, 'message': 'Job not found'})
            
            if existing:
                cursor.execute(arks WHERE user_id = %s AND job_id = %s", 
                    "DELETE FROM bookmarks WHERE user_id = %s AND job_id = %s",user_id, job_id)
                    (user_id, job_id)
                )ing = cursor.fetchone()
                saved = False
            else:
                cursor.execute(
                    "INSERT INTO bookmarks (user_id, job_id) VALUES (%s, %s)",   "DELETE FROM bookmarks WHERE user_id = %s AND job_id = %s",
                    (user_id, job_id), job_id)
                ))
                saved = Truealse
                
            conn.commit()    cursor.execute(
            return jsonify({'success': True, 'saved': saved})T INTO bookmarks (user_id, job_id) VALUES (%s, %s)",
            
    except Exception as e:
        app.logger.error(f"Error saving job: {str(e)}")                saved = True
        return jsonify({'success': False, 'message': 'Database error occurred'})

@app.route('/get_job_status/<int:job_id>')cess': True, 'saved': saved})
def get_job_status(job_id):
    if 'user_id' not in session:pt Exception as e:
        return jsonify({'success': False, 'message': 'Please log in first', 'saved': False}) saving job: {str(e)}")
        lse, 'message': 'Database error occurred'})
    user_id = session['user_id']
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bookmarks WHERE user_id = %s AND job_id = %s", 
                      (user_id, job_id))({'success': False, 'message': 'Please log in first', 'saved': False})
        saved = cursor.fetchone() is not None
        cursor.close()
            with get_db_connection() as conn:
    return jsonify({'success': True, 'saved': saved})
ecute("SELECT * FROM bookmarks WHERE user_id = %s AND job_id = %s", 
@app.route('/saved_jobs', methods=['GET'])job_id))
def saved_jobs():
    if 'user_id' not in session:
        flash("Please log in first.", "warning")        
        return redirect(url_for('home'))rue, 'saved': saved})

    user_id = session['user_id']
    with get_db_connection() as conn:def saved_jobs():
        cursor = conn.cursor(dictionary=True)ssion:

        cursor.execute("""l_for('home'))
            SELECT jobs.*, bookmarks.created_at AS saved_at, users.full_name, users.profile_picture
            FROM bookmarks
            JOIN jobs ON bookmarks.job_id = jobs.id
            JOIN users ON jobs.posted_by = users.id
            WHERE bookmarks.user_id = %s
            ORDER BY bookmarks.created_at DESC
        """, (user_id,))s.*, bookmarks.created_at AS saved_at, users.full_name, users.profile_picture
        saved_jobs = cursor.fetchall()            FROM bookmarks
        cursor.close()
            JOIN users ON jobs.posted_by = users.id
    return render_template('saved_jobs.html', saved_jobs=saved_jobs)kmarks.user_id = %s
Y bookmarks.created_at DESC
@app.route('/health')""", (user_id,))
def health_check():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()aved_jobs.html', saved_jobs=saved_jobs)
            cursor.execute('SELECT 1')
            cursor.fetchone()
            cursor.close()
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        app.logger.error(f"Health check failed: {str(e)}")            cursor = conn.cursor()
        return jsonify({"status": "unhealthy", "database": "disconnected", "error": str(e)}), 500'SELECT 1')
fetchone()
@app.route('/drop_indexes')    cursor.close()
def drop_indexes():y", "database": "connected"}), 200
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()ed", "error": str(e)}), 500
            cursor.execute("DROP INDEX idx_animal_search ON animals")
            cursor.execute("DROP INDEX idx_animal_created ON animals"))
            conn.commit()
            cursor.close()
        return "Indexes dropped successfully"
    except Exception as e:            cursor = conn.cursor()
        return f"Error dropping indexes: {str(e)}"r.execute("DROP INDEX idx_animal_search ON animals")
NDEX idx_animal_created ON animals")
if not app.debug:)
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/rural_jobs.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(  return f"Error dropping indexes: {str(e)}"
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)    file_handler = RotatingFileHandler('logs/rural_jobs.log', maxBytes=10240, backupCount=10)
    app.logger.info('Rural Jobs startup')atter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
app.jinja_env.filters['escapejs'] = escape
ogging.INFO)
@app.errorhandler(404)
def not_found_error(error):    app.logger.setLevel(logging.INFO)
    return render_template('errors/404.html'), 404ural Jobs startup')

@app.errorhandler(500)a_env.filters['escapejs'] = escape
def internal_error(error):
    try:)
        db = get_db_connection()r(error):
        db.rollback()('errors/404.html'), 404
        db.close()
    except Exception as e:.errorhandler(500)
        app.logger.error(f"Error handling 500 error: {str(e)}")
    
    app.logger.error('Server Error: %s', str(error))
    app.logger.error(traceback.format_exc())        db.rollback()
    return render_template('errors/500.html'), 500

if __name__ == '__main__':ing 500 error: {str(e)}")


    app.run(host='0.0.0.0', port=port)    port = int(os.environ.get("PORT", 5000))    
    app.logger.error('Server Error: %s', str(error))
    app.logger.error(traceback.format_exc())
    return render_template('errors/500.html'), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)