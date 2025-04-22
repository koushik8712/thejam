CREATE TABLE otp_verifications (
    id INT PRIMARY KEY AUTO_INCREMENT,
    phone_number VARCHAR(15) NOT NULL,
    otp VARCHAR(6) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    is_used BOOLEAN DEFAULT FALSE,
    INDEX phone_idx (phone_number),
    INDEX otp_idx (otp)
);
