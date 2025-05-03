-- Clear bookmarks first (due to foreign key constraints)
DELETE FROM bookmarks;
DELETE FROM animal_bookmarks;

-- Clear main content tables
DELETE FROM jobs;
DELETE FROM animals;

-- Clear user related tables
DELETE FROM otp_verifications;
DELETE FROM password_resets;

-- Clear users last (since other tables reference it)
DELETE FROM users;

-- Reset auto increment counters
ALTER TABLE bookmarks AUTO_INCREMENT = 1;
ALTER TABLE animal_bookmarks AUTO_INCREMENT = 1;
ALTER TABLE jobs AUTO_INCREMENT = 1;
ALTER TABLE animals AUTO_INCREMENT = 1;
ALTER TABLE users AUTO_INCREMENT = 1;
ALTER TABLE otp_verifications AUTO_INCREMENT = 1;
ALTER TABLE password_resets AUTO_INCREMENT = 1;
