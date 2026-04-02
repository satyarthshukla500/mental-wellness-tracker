from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Relationship to wellness entries
    wellness_entries = db.relationship('WellnessEntry', backref='user', lazy=True)
    reminder_settings = db.relationship('ReminderSetting', backref='user', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'

class WellnessEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    mood = db.Column(db.String(20), nullable=False)  # e.g., 'Happy', 'Sad', 'Anxious', 'Calm'
    intensity = db.Column(db.Integer, nullable=False, default=3)  # 1-5 scale for mood intensity
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __init__(self, **kwargs):
        super(WellnessEntry, self).__init__(**kwargs)
        # Ensure intensity is always valid
        if self.intensity is None or self.intensity < 1 or self.intensity > 5:
            self.intensity = 3  # Default to middle value
    
    def set_intensity(self, value):
        """Set intensity with validation"""
        if value is None or value < 1 or value > 5:
            raise ValueError("Intensity must be between 1 and 5")
        self.intensity = value

    def __repr__(self):
        return f'<WellnessEntry {self.mood} by {self.user.username}>'

class ReminderSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    # Store daily reminder time in 12-hour format as user entered it
    reminder_time_utc = db.Column(db.String(10), nullable=True)  # e.g., '3:30 PM'
    channel = db.Column(db.String(20), default='in_app', nullable=False)  # 'in_app' or 'email'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False, nullable=False)

class Admin(db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

class ContactMessage(db.Model):
    __tablename__ = 'contact_messages'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    date_submitted = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)

class LoginAttempt(db.Model):
    __tablename__ = 'login_attempt'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, unique=True)  # IPv4/IPv6
    attempt_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_attempt_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<LoginAttempt {self.ip_address} - {self.attempt_count} attempts>'