CREATE TABLE local_prices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    commodity VARCHAR(100) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    market VARCHAR(100) NOT NULL,
    district VARCHAR(100) NOT NULL,
    submitted_by INT NOT NULL,
    submitted_at DATETIME NOT NULL,
    FOREIGN KEY (submitted_by) REFERENCES users(id)
);
