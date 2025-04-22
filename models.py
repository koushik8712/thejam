from app import db
from datetime import datetime

class Job(db.Model):
    __tablename__ = 'jobs'  # optional, but good to be explicit

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(255), nullable=False)
    salary = db.Column(db.String(100))
    phone_number = db.Column(db.String(15), nullable=False)
    posted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    latitude = db.Column(db.Float, nullable=True)  # Latitude for geolocation
    longitude = db.Column(db.Float, nullable=True)  # Longitude for geolocation
