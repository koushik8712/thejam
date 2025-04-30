CREATE TABLE animal_bookmarks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    animal_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (animal_id) REFERENCES animals(id),
    UNIQUE KEY unique_animal_bookmark (user_id, animal_id)
);
