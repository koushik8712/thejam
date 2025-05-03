import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def init_database():
    db_config = {
        'host': os.getenv('DB_HOST'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME'),
        'port': int(os.getenv('DB_PORT', '3306')),
        'auth_plugin': 'mysql_native_password'
    }

    # SQL statements to create tables
    tables = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            full_name VARCHAR(100) NOT NULL,
            phone_number VARCHAR(15) NOT NULL UNIQUE,
            gender VARCHAR(20) DEFAULT 'Not specified',
            bio TEXT,
            location VARCHAR(100),
            profile_picture VARCHAR(255) DEFAULT 'default_profile.png',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(100) NOT NULL,
            description TEXT NOT NULL,
            location VARCHAR(100) NOT NULL,
            salary VARCHAR(50),
            phone_number VARCHAR(15) NOT NULL,
            job_type ENUM('full_time', 'part_time', 'contract') DEFAULT 'full_time',
            posted_by INT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (posted_by) REFERENCES users(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS animals (
            id INT AUTO_INCREMENT PRIMARY KEY,
            category VARCHAR(100) NOT NULL,
            age INT NULL,
            breed VARCHAR(100) NULL,
            weight FLOAT NOT NULL,
            cost FLOAT NOT NULL,
            description TEXT,
            location VARCHAR(255) NOT NULL,
            contact_number VARCHAR(15) NOT NULL,
            photos TEXT NOT NULL,
            posted_by INT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (posted_by) REFERENCES users(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bookmarks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            job_id INT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
            UNIQUE KEY unique_bookmark (user_id, job_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS animal_bookmarks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            animal_id INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (animal_id) REFERENCES animals(id) ON DELETE CASCADE,
            UNIQUE KEY unique_animal_bookmark (user_id, animal_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS password_resets (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            token VARCHAR(255) NOT NULL,
            expires_at DATETIME NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS otp_verifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            phone_number VARCHAR(15) NOT NULL,
            otp VARCHAR(6) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            is_used BOOLEAN DEFAULT FALSE
        )
        """
    ]

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        print("Connected to database, creating tables...")
        for table in tables:
            cursor.execute(table)
            print("Table created successfully")
        
        conn.commit()
        print("All tables created successfully!")
        
    except mysql.connector.Error as e:
        print(f"Error: {e}")
        raise
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn.is_connected():
            conn.close()

if __name__ == "__main__":
    init_database()
