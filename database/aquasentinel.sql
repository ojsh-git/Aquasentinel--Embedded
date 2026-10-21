CREATE DATABASE aquasentinel;

USE aquasentinel;
CREATE TABLE sensor_readings (
    id INT AUTO_INCREMENT PRIMARY KEY,

    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,

    distance_cm DECIMAL(8,2),
    level_cm DECIMAL(8,2),
    water_level DECIMAL(6,2),

    rise_rate DECIMAL(8,2),

    rain_percentage DECIMAL(6,2),
    rain_detected BOOLEAN,

    risk_score DECIMAL(6,2),
    risk_level VARCHAR(20),

    predicted_level DECIMAL(6,2),

    gate_status VARCHAR(10)
);
CREATE TABLE devices (
    device_id INT AUTO_INCREMENT PRIMARY KEY,
    device_name VARCHAR(100) NOT NULL,
    location VARCHAR(150),
    status VARCHAR(20) DEFAULT 'OFFLINE',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO devices
(device_name, location, status)
VALUES
('AquaSentinel-01', 'Prototype Test Area', 'ONLINE');
CREATE TABLE sensor_readings (
    reading_id INT AUTO_INCREMENT PRIMARY KEY,

    device_id INT NOT NULL,

    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,

    distance_cm DECIMAL(8,2),
    level_cm DECIMAL(8,2),
    water_level DECIMAL(6,2),

    rise_rate DECIMAL(8,2),

    rain_percentage DECIMAL(6,2),
    rain_detected BOOLEAN,

    FOREIGN KEY (device_id)
        REFERENCES devices(device_id)
);
CREATE TABLE risk_assessments (
    risk_id INT AUTO_INCREMENT PRIMARY KEY,

    reading_id INT NOT NULL,

    risk_score DECIMAL(6,2),
    risk_level VARCHAR(20),

    predicted_level DECIMAL(6,2),

    gate_status VARCHAR(10),

    recommendation VARCHAR(255),

    FOREIGN KEY (reading_id)
        REFERENCES sensor_readings(reading_id)
);
