USE railway;

INSERT INTO users (
    username, 
    password, 
    full_name, 
    phone_number, 
    gender,
    location
) VALUES (
    'testuser',
    '$2b$12$MAKoAcf3t7T7RUdFwnSnGOPTsjujvDvFKGI988UMcs0wagnK3AQum', -- Password is 'password123'
    'Test User',
    '1234567890',
    'Not specified',
    'Test Location'
);
