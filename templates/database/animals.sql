CREATE TABLE IF NOT EXISTS animals (
    id INT PRIMARY KEY AUTO_INCREMENT,
    category VARCHAR(50) NOT NULL,
    breed VARCHAR(100),
    age INT,
    weight DECIMAL(10,2),
    cost DECIMAL(10,2),
    description TEXT,
    location VARCHAR(255),
    photo VARCHAR(255),
    contact_number VARCHAR(15),
    user_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_animal_search ON animals(category, breed, location);
CREATE INDEX idx_animal_created ON animals(created_at);
