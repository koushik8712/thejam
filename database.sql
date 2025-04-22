-- Drop existing table if it exists
DROP TABLE IF EXISTS otp_verifications;

CREATE TABLE IF NOT EXISTS otp_verifications (
    id INT PRIMARY KEY AUTO_INCREMENT,
    phone_number VARCHAR(15) NOT NULL,
    otp VARCHAR(6) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    is_used BOOLEAN DEFAULT FALSE,
    INDEX (phone_number),
    INDEX (otp)
);

-- Ensure users table has phone_number column
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR(15) UNIQUE;
