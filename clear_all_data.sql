-- Disable foreign key checks temporarily
SET FOREIGN_KEY_CHECKS = 0;

-- Clear chat and bookmark related tables first
DELETE FROM chat_messages;
DELETE FROM bookmarks;
DELETE FROM animal_bookmarks;
DELETE FROM saved_jobs;

-- Clear content tables
DELETE FROM animals;
DELETE FROM jobs;
DELETE FROM local_prices;

-- Clear authentication related tables
DELETE FROM password_resets;
DELETE FROM otp_verifications;

-- Clear users table last
DELETE FROM users;

-- Reset auto increment counters
ALTER TABLE chat_messages AUTO_INCREMENT = 1;
ALTER TABLE bookmarks AUTO_INCREMENT = 1;
ALTER TABLE animal_bookmarks AUTO_INCREMENT = 1;
ALTER TABLE saved_jobs AUTO_INCREMENT = 1;
ALTER TABLE animals AUTO_INCREMENT = 1;
ALTER TABLE jobs AUTO_INCREMENT = 1;
ALTER TABLE local_prices AUTO_INCREMENT = 1;
ALTER TABLE password_resets AUTO_INCREMENT = 1;
ALTER TABLE otp_verifications AUTO_INCREMENT = 1;
ALTER TABLE users AUTO_INCREMENT = 1;

-- Re-enable foreign key checks
SET FOREIGN_KEY_CHECKS = 1;
