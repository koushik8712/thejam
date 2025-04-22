import bcrypt
import mysql.connector

# Database Connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="projectjam@123",
    database="rural_job_portal"
)
cursor = db.cursor()

# Hash Password
password = "test123"
hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

# Insert User
query = "INSERT INTO users (username, password) VALUES (%s, %s)"
cursor.execute(query, ('testuser2', hashed_password.decode('utf-8')))
db.commit()

print("User inserted successfully with hashed password.")
