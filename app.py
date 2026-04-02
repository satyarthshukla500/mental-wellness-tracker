import os
import re
from forms import RegistrationForm, WellnessEntryForm
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, WellnessEntry, ReminderSetting, Notification, Admin, ContactMessage, LoginAttempt
from config import config

# Login rate limiting configuration
MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_DURATION_MINUTES = 15
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes
from flask import Flask, render_template, redirect, url_for, flash, abort, jsonify, make_response, request
import csv
import io
from datetime import datetime, timedelta
from forms import LoginForm, DeleteEntryForm, ReminderForm, ChangePasswordForm, DeleteAccountForm, ProfileForm, AdminChangePasswordForm
from flask import session
from apscheduler.schedulers.background import BackgroundScheduler
import smtplib
from email.message import EmailMessage
import random
from flask_wtf.csrf import CSRFProtect
# from flask_migrate import Migrate  # Temporarily disabled

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-fallback-key')

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Better database configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:////tmp/wellness.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Initialize Flask-Migrate
# migrate = Migrate(app, db)  # Temporarily disabled

# Create database tables
with app.app_context():
    db.create_all()

# -------------------- Wellness Tips Helper Functions --------------------

def analyze_mood_patterns(user_id, days=14):
    """Analyze user's mood patterns over the last N days"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get recent entries
    recent_entries = WellnessEntry.query.filter(
        WellnessEntry.user_id == user_id,
        WellnessEntry.created_at >= start_date,
        WellnessEntry.created_at <= end_date
    ).order_by(WellnessEntry.created_at.desc()).all()
    
    if not recent_entries:
        return None
    
    # Mood scoring system
    mood_scores = {
        'Happy': 5, 'Excited': 5, 'Grateful': 4, 'Proud': 4, 'Hopeful': 4, 'Content': 4,
        'Calm': 3, 'Tired': 2, 'Confused': 2,
        'Sad': 1, 'Anxious': 1, 'Frustrated': 1, 'Lonely': 1, 'Overwhelmed': 1
    }
    
    # Analyze patterns
    moods = [entry.mood for entry in recent_entries]
    scores = [entry.intensity for entry in recent_entries]  # Use actual intensity values from database
    
    # Calculate statistics
    avg_score = sum(scores) / len(scores) if scores else 0
    recent_trend = scores[:3] if len(scores) >= 3 else scores  # Last 3 entries
    
    # Count mood frequencies
    mood_counts = {}
    for mood in moods:
        mood_counts[mood] = mood_counts.get(mood, 0) + 1
    
    most_common_mood = max(mood_counts.items(), key=lambda x: x[1])[0] if mood_counts else None
    
    # Determine trend direction
    trend_direction = "stable"
    if len(recent_trend) >= 2:
        if recent_trend[0] > recent_trend[-1]:
            trend_direction = "improving"
        elif recent_trend[0] < recent_trend[-1]:
            trend_direction = "declining"
    
    return {
        'total_entries': len(recent_entries),
        'avg_score': avg_score,
        'most_common_mood': most_common_mood,
        'trend_direction': trend_direction,
        'mood_counts': mood_counts,
        'recent_scores': recent_trend,
        'days_analyzed': days
    }

def generate_wellness_tips(mood_analysis):
    """Generate personalized wellness tips based on mood analysis"""
    if not mood_analysis:
        return [{
            'title': 'Start Your Wellness Journey',
            'tip': 'Begin by adding your first mood entry to receive personalized wellness tips!',
            'category': 'getting_started',
            'priority': 'high'
        }]
    
    tips = []
    avg_score = mood_analysis['avg_score']
    most_common_mood = mood_analysis['most_common_mood']
    trend_direction = mood_analysis['trend_direction']
    mood_counts = mood_analysis['mood_counts']
    
    # Tip categories and their tips
    tip_categories = {
        'low_mood': {
            'title': 'Self-Care & Support',
            'tips': [
                'Consider reaching out to a trusted friend or family member for support. Sometimes sharing our feelings can lighten the emotional load.',
                'Try a 5-minute mindfulness exercise: focus on your breathing and notice three things you can see, hear, and feel right now.',
                'Engage in gentle physical activity like a short walk or stretching. Movement can help improve mood and reduce stress.'
            ]
        },
        'anxiety_stress': {
            'title': 'Calm & Grounding',
            'tips': [
                'Practice the 4-7-8 breathing technique: inhale for 4 counts, hold for 7, exhale for 8. Repeat 3-4 times.',
                'Create a "worry time" - set aside 10 minutes daily to write down concerns, then let them go until tomorrow.',
                'Try progressive muscle relaxation: tense and release each muscle group from toes to head for 5 seconds each.'
            ]
        },
        'positive_streak': {
            'title': 'Maintain & Build',
            'tips': [
                'Keep up the great work! Consider journaling about what\'s contributing to your positive mood to reinforce these patterns.',
                'Share your positive energy by doing something kind for someone else - it often amplifies our own happiness.',
                'Create a gratitude practice: write down three things you\'re grateful for each day to maintain this positive momentum.'
            ]
        },
        'improving_trend': {
            'title': 'Keep the Momentum',
            'tips': [
                'You\'re on an upward trend! Identify what strategies are working and continue practicing them regularly.',
                'Celebrate small wins and acknowledge your progress. Positive reinforcement helps maintain motivation.',
                'Consider setting small, achievable wellness goals to continue building on your current positive trajectory.'
            ]
        },
        'general_wellness': {
            'title': 'Daily Wellness',
            'tips': [
                'Maintain a consistent sleep schedule - aim for 7-9 hours of quality sleep each night.',
                'Stay hydrated and eat regular, balanced meals to support both physical and mental well-being.',
                'Take regular breaks from screens and spend time in nature or doing activities you enjoy.'
            ]
        }
    }
    
    # Determine which tips to show based on patterns
    if avg_score <= 2.5:  # Low mood patterns
        tips.append({
            'title': tip_categories['low_mood']['title'],
            'tip': random.choice(tip_categories['low_mood']['tips']),
            'category': 'low_mood',
            'priority': 'high'
        })
    
    # Check for anxiety/stress patterns
    stress_moods = ['Anxious', 'Frustrated', 'Overwhelmed']
    if any(mood in mood_counts for mood in stress_moods):
        stress_count = sum(mood_counts.get(mood, 0) for mood in stress_moods)
        if stress_count >= mood_analysis['total_entries'] * 0.3:  # 30% or more stress moods
            tips.append({
                'title': tip_categories['anxiety_stress']['title'],
                'tip': random.choice(tip_categories['anxiety_stress']['tips']),
                'category': 'anxiety_stress',
                'priority': 'high'
            })
    
    # Positive patterns
    if avg_score >= 4.0:  # High mood patterns
        tips.append({
            'title': tip_categories['positive_streak']['title'],
            'tip': random.choice(tip_categories['positive_streak']['tips']),
            'category': 'positive_streak',
            'priority': 'medium'
        })
    
    # Trend-based tips
    if trend_direction == 'improving':
        tips.append({
            'title': tip_categories['improving_trend']['title'],
            'tip': random.choice(tip_categories['improving_trend']['tips']),
            'category': 'improving_trend',
            'priority': 'medium'
        })
    
    # Always include a general wellness tip
    tips.append({
        'title': tip_categories['general_wellness']['title'],
        'tip': random.choice(tip_categories['general_wellness']['tips']),
        'category': 'general_wellness',
        'priority': 'low'
    })
    
    # Limit to 3 tips maximum
    return tips[:3]

# -------------------- Reminders: scheduler setup --------------------
scheduler = BackgroundScheduler(daemon=True)

def convert_12hour_to_24hour(time_12h):
    """Convert 12-hour format to 24-hour format.
    
    Args:
        time_12h: Time in format like '1:22 PM' or '01:22 PM'
    
    Returns:
        24-hour time string in format 'HH:MM'
    """
    try:
        time_12h = time_12h.strip().upper()
        match = re.match(r'^(\d{1,2}):(\d{2})\s*(AM|PM)?$', time_12h)
        
        if not match:
            return time_12h  # return as-is if not valid format
        
        hours = int(match.group(1))
        minutes = match.group(2)
        period = match.group(3)
        
        if period == 'PM' and hours != 12:
            hours += 12
        elif period == 'AM' and hours == 12:
            hours = 0
        
        return f"{hours:02d}:{minutes}"
    except Exception as e:
        print(f"Error converting 12-hour time {time_12h}: {e}")
        return time_12h

def convert_24hour_to_12hour(time_24h):
    """Convert 24-hour format to 12-hour format.
    
    Args:
        time_24h: Time in format 'HH:MM' (24-hour)
    
    Returns:
        12-hour time string in format 'H:MM AM/PM'
    """
    try:
        hour, minute = map(int, time_24h.split(':'))
        period = 'AM' if hour < 12 else 'PM'
        
        if hour == 0:
            hour = 12
        elif hour > 12:
            hour -= 12
        
        return f"{hour}:{minute:02d} {period}"
    except Exception as e:
        print(f"Error converting 24-hour time {time_24h}: {e}")
        return time_24h

def convert_local_to_utc(local_time_str, timezone_offset_minutes):
    """Convert local time string to UTC time string.
    
    Args:
        local_time_str: Time in format 'HH:MM' (24-hour)
        timezone_offset_minutes: Timezone offset in minutes (e.g., -300 for EST)
    
    Returns:
        UTC time string in format 'HH:MM'
    """
    try:
        # Parse local time
        hour, minute = map(int, local_time_str.split(':'))
        
        # Create datetime object for today with local time
        local_dt = datetime.utcnow().replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Convert to UTC by subtracting the offset
        utc_dt = local_dt - timedelta(minutes=timezone_offset_minutes)
        
        return utc_dt.strftime('%H:%M')
    except Exception as e:
        print(f"Error converting time {local_time_str}: {e}")
        return local_time_str

def get_user_timezone_offset():
    """Get user's timezone offset from JavaScript."""
    # This will be called from the frontend via AJAX
    return request.json.get('timezone_offset', 0) if request.is_json else 0

def _send_email(to_email: str, subject: str, body: str) -> bool:
    """Send email reminder. Returns True if successful, False otherwise."""
    # Get SMTP configuration from environment variables
    host = os.getenv('SMTP_HOST')
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASSWORD')
    port = int(os.getenv('SMTP_PORT', '587'))
    
    # Check if email configuration is available
    if not (host and user and password and to_email):
        print(f"Email not configured or missing recipient: {to_email}")
        return False
    
    try:
        # Create email message
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = user
        msg['To'] = to_email
        msg.set_content(body)
        
        # Send email
        with smtplib.SMTP(host, port) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
        
        print(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        print(f"Failed to send email to {to_email}: {str(e)}")
        return False

def run_reminder_tick():
    """Run reminder tick - check for users who need reminders and send them."""
    now = datetime.now()  # Use local time
    current_hour = now.hour
    current_minute = now.minute
    current_second = now.second
    
    # Create multiple time format variations for comparison
    current_12h_variations = [
        now.strftime('%I:%M %p').lstrip('0'),  # "3:30 PM"
        now.strftime('%I:%M %p'),              # "03:30 PM" 
        now.strftime('%I:%M %p').replace(' 0', ' '),  # "3:30 PM" (no leading zero)
    ]
    
    with app.app_context():
        # Get all enabled reminder settings
        settings = ReminderSetting.query.filter_by(enabled=True).all()
        
        if settings:
            print(f"Reminder tick: {now.strftime('%H:%M:%S')} ({now.strftime('%I:%M %p')}) - Checking {len(settings)} settings")
        
        for setting in settings:
            if not setting.reminder_time_utc:
                continue
                
            user = User.query.get(setting.user_id)
            if not user:
                print(f"User not found for setting {setting.id}")
                continue
            
            # Normalize the stored time for comparison
            stored_time = setting.reminder_time_utc.strip()
            
            # Check if current time matches any of the stored time formats
            time_matches = False
            for current_format in current_12h_variations:
                if stored_time == current_format:
                    time_matches = True
                    break
            
            # Also check if the stored time matches current time with different formatting
            try:
                # Try to parse the stored time and compare with current time
                from datetime import datetime
                stored_dt = datetime.strptime(stored_time, '%I:%M %p')
                current_dt = datetime.strptime(now.strftime('%I:%M %p'), '%I:%M %p')
                
                if stored_dt.hour == current_dt.hour and stored_dt.minute == current_dt.minute:
                    time_matches = True
            except ValueError:
                pass
            
            # Additional check: if we're within the first 10 seconds of the target minute
            if time_matches and current_second <= 10:
                # Check if we already sent a notification today
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                
                existing = Notification.query.filter(
                    Notification.user_id == user.id,
                    Notification.message == 'Time to record your mood for today!',
                    Notification.created_at >= today_start,
                    Notification.created_at <= today_end
                ).first()
                
                if existing:
                    print(f"Skipping duplicate notification for user {user.username}")
                    continue
                
                # Create in-app notification
                note = Notification(user_id=user.id, message='Time to record your mood for today!')
                db.session.add(note)
                db.session.commit()
                print(f"✅ EXACT TIME: Created notification for {user.username} at {now.strftime('%H:%M:%S')}")
                
                # Send email if configured and user has email
                if setting.channel == 'email' and user.email:
                    email_sent = _send_email(
                        user.email, 
                        'Daily Wellness Reminder', 
                        f'Hi {user.username},\n\nIt\'s time to record your mood for today! Log in to your wellness tracker to add your daily entry.\n\nBest regards,\nYour Wellness Tracker'
                    )
                    if email_sent:
                        print(f"📧 Email reminder sent to {user.email}")
                    else:
                        print(f"❌ Failed to send email reminder to {user.email}")
                elif setting.channel == 'email' and not user.email:
                    print(f"⚠️ User {user.username} has email reminders enabled but no email address")
            elif not time_matches:
                # Debug: show what times we're checking (only occasionally)
                if now.second < 5:  # Only log occasionally to avoid spam
                    print(f"🔍 Checking {user.username}: stored='{stored_time}' vs current='{now.strftime('%I:%M %p')}'")

def schedule_reminders():
    """Schedule individual reminder jobs for each user's exact time"""
    with app.app_context():
        settings = ReminderSetting.query.filter_by(enabled=True).all()
        
        for setting in settings:
            if not setting.reminder_time_utc:
                continue
                
            try:
                # Parse the reminder time
                reminder_time = datetime.strptime(setting.reminder_time_utc.strip(), '%I:%M %p')
                
                # Create a job for this specific time
                job_id = f'reminder_{setting.user_id}'
                
                # Schedule the job to run at the exact time every day with high precision
                scheduler.add_job(
                    func=send_reminder_for_user,
                    trigger='cron',
                    hour=reminder_time.hour,
                    minute=reminder_time.minute,
                    second=0,  # Exact second
                    args=[setting.user_id],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=1,  # Allow 1 second grace period
                    coalesce=True,  # Combine multiple missed executions
                    max_instances=1  # Only one instance at a time
                )
                
                print(f"✅ Scheduled EXACT reminder for user {setting.user_id} at {setting.reminder_time_utc} (job: {job_id})")
                
            except ValueError as e:
                print(f"Error parsing time for user {setting.user_id}: {setting.reminder_time_utc} - {e}")

def send_reminder_for_user(user_id):
    """Send reminder for a specific user at exact time"""
    with app.app_context():
        user = User.query.get(user_id)
        if not user:
            print(f"User {user_id} not found")
            return
            
        setting = ReminderSetting.query.filter_by(user_id=user_id, enabled=True).first()
        if not setting:
            print(f"No reminder setting for user {user_id}")
            return
        
        # Check if we already sent a notification today
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        existing = Notification.query.filter(
            Notification.user_id == user_id,
            Notification.message == 'Time to record your mood for today!',
            Notification.created_at >= today_start,
            Notification.created_at <= today_end
        ).first()
        
        if existing:
            print(f"Skipping duplicate notification for user {user.username}")
            return
        
        # Create in-app notification
        note = Notification(user_id=user_id, message='Time to record your mood for today!')
        db.session.add(note)
        db.session.commit()
        print(f"✅ EXACT TIME: Created notification for {user.username} at {now.strftime('%H:%M:%S')}")
        
        # Send email if configured and user has email
        if setting.channel == 'email' and user.email:
            email_sent = _send_email(
                user.email, 
                'Daily Wellness Reminder', 
                f'Hi {user.username},\n\nIt\'s time to record your mood for today! Log in to your wellness tracker to add your daily entry.\n\nBest regards,\nYour Wellness Tracker'
            )
            if email_sent:
                print(f"📧 Email reminder sent to {user.email}")
            else:
                print(f"❌ Failed to send email reminder to {user.email}")
        elif setting.channel == 'email' and not user.email:
            print(f"⚠️ User {user.username} has email reminders enabled but no email address")

def backup_reminder_check():
    """Backup system that checks every second during target minutes"""
    now = datetime.now()
    
    with app.app_context():
        settings = ReminderSetting.query.filter_by(enabled=True).all()
        
        for setting in settings:
            if not setting.reminder_time_utc:
                continue
                
            try:
                # Parse the reminder time
                reminder_time = datetime.strptime(setting.reminder_time_utc.strip(), '%I:%M %p')
                
                # Check if we're in the target minute and second is 0-2
                if (now.hour == reminder_time.hour and 
                    now.minute == reminder_time.minute and 
                    now.second <= 2):
                    
                    user = User.query.get(setting.user_id)
                    if not user:
                        continue
                    
                    # Check if we already sent a notification today
                    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                    
                    existing = Notification.query.filter(
                        Notification.user_id == setting.user_id,
                        Notification.message == 'Time to record your mood for today!',
                        Notification.created_at >= today_start,
                        Notification.created_at <= today_end
                    ).first()
                    
                    if not existing:
                        # Create in-app notification
                        note = Notification(user_id=setting.user_id, message='Time to record your mood for today!')
                        db.session.add(note)
                        db.session.commit()
                        print(f"🚨 BACKUP TRIGGER: Created notification for {user.username} at {now.strftime('%H:%M:%S')}")
                        
            except ValueError:
                pass

if not scheduler.running:
    # Start the scheduler
    scheduler.start()
    print("Reminder scheduler started with exact-time scheduling")
    
    # Schedule all existing reminders
    schedule_reminders()
    
    # Add backup polling every second during target minutes
    scheduler.add_job(
        backup_reminder_check,
        'interval',
        seconds=1,
        id='backup_reminder_check',
        replace_existing=True
    )
    print("Backup reminder system started - checking every second")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about_us.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        
        # Basic validation
        if not all([name, email, subject, message]):
            flash('Please fill in all required fields.', 'danger')
            return render_template('contact_support.html')
        
        # Email validation
        import re
        email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_pattern, email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('contact_support.html')
        
        # Save to database
        contact_msg = ContactMessage(
            name=name,
            email=email,
            subject=subject,
            message=message
        )
        db.session.add(contact_msg)
        db.session.commit()
        
        flash('Thank you for contacting us! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    
    # Clear any existing flash messages and session data when loading the contact page
    from flask import get_flashed_messages
    get_flashed_messages()
    
    # Clear any problematic session variables
    session.pop('_flashes', None)
    
    return render_template('contact_support.html')  

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        # Pre-validate uniqueness for a friendly message
        existing_username = User.query.filter_by(username=form.username.data).first()
        if existing_username:
            flash('Username is already taken. Please choose another.', 'danger')
            return render_template('register.html', form=form)

        existing_email = User.query.filter_by(email=form.email.data).first()
        if existing_email:
            flash('Email is already registered. Try logging in.', 'danger')
            return render_template('register.html', form=form)

        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data)
        )
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('That username or email is already in use.', 'danger')
            return render_template('register.html', form=form)

        # Automatically log in the user after successful registration
        session['user_id'] = user.id
        flash("Registration successful! Welcome to your wellness dashboard!", "success")
        return redirect(url_for('dashboard'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            session['user_id'] = user.id
            flash('Logged in successfully! Welcome back to your wellness dashboard!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You were logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    # Get the current user
    user = User.query.get(session['user_id'])
    
    # Filter controls - support custom date range
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    month_str = request.args.get('month') or datetime.utcnow().strftime('%Y-%m')
    date_str = request.args.get('date') or ''

    # Determine date range to use
    filter_start = None
    filter_end = None
    filter_type = 'month'  # 'month', 'date', 'custom'
    
    # Priority: custom range > single date > month
    if start_date_str and end_date_str:
        try:
            filter_start = datetime.strptime(start_date_str, '%Y-%m-%d')
            filter_end = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)  # Include end date
            filter_type = 'custom'
        except Exception:
            pass
    
    if not filter_start and date_str:
        try:
            y, m, d = [int(p) for p in date_str.split('-')]
            filter_start = datetime(y, m, d)
            filter_end = filter_start + timedelta(days=1)
            filter_type = 'date'
        except Exception:
            pass
    
    if not filter_start:
        # Default to month
        try:
            year, month = [int(part) for part in month_str.split('-')]
            filter_start = datetime(year, month, 1)
            if month == 12:
                filter_end = datetime(year + 1, 1, 1)
            else:
                filter_end = datetime(year, month + 1, 1)
        except Exception:
            filter_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if filter_start.month == 12:
                filter_end = datetime(filter_start.year + 1, 1, 1)
            else:
                filter_end = datetime(filter_start.year, filter_start.month + 1, 1)
            month_str = filter_start.strftime('%Y-%m')

    # Entries for selected date range (latest first)
    entries = WellnessEntry.query.filter(
        WellnessEntry.user_id == user.id,
        WellnessEntry.created_at >= filter_start,
        WellnessEntry.created_at < filter_end
    ).order_by(WellnessEntry.created_at.desc()).limit(10).all()
    
    # Analytics data for selected date range
    mood_counts = db.session.query(WellnessEntry.mood, db.func.count(WellnessEntry.id)).filter(
        WellnessEntry.user_id == user.id,
        WellnessEntry.created_at >= filter_start,
        WellnessEntry.created_at < filter_end
    ).group_by(WellnessEntry.mood).all()
    total_entries = WellnessEntry.query.filter(
        WellnessEntry.user_id == user.id,
        WellnessEntry.created_at >= filter_start,
        WellnessEntry.created_at < filter_end
    ).count()
    most_common_mood = max(mood_counts, key=lambda x: x[1])[0] if mood_counts else "No entries yet"
    
    # Enhanced analytics - mood scoring and best/worst days
    mood_scores = {
        'Happy': 5, 'Excited': 5, 'Grateful': 4,
        'Calm': 3, 'Tired': 2, 'Sad': 1, 
        'Anxious': 1, 'Frustrated': 1
    }
    
    # Calculate daily mood averages and find best/worst days
    daily_moods = {}
    all_entries_in_range = WellnessEntry.query.filter(
        WellnessEntry.user_id == user.id,
        WellnessEntry.created_at >= filter_start,
        WellnessEntry.created_at < filter_end
    ).order_by(WellnessEntry.created_at.asc()).all()
    
    for entry in all_entries_in_range:
        date_key = entry.created_at.date()
        if date_key not in daily_moods:
            daily_moods[date_key] = []
        daily_moods[date_key].append(entry.intensity)
    
    # Calculate daily averages
    daily_averages = {}
    for date, scores in daily_moods.items():
        daily_averages[date] = sum(scores) / len(scores)
    
    # Find best and worst days
    best_day = None
    worst_day = None
    if daily_averages:
        best_day = max(daily_averages.items(), key=lambda x: x[1])
        worst_day = min(daily_averages.items(), key=lambda x: x[1])
    
    # Calculate overall average mood score
    overall_average = sum(daily_averages.values()) / len(daily_averages) if daily_averages else 0
    
    delete_form = DeleteEntryForm()
    # Fetch unread notifications for the header
    notifications = Notification.query.filter_by(user_id=user.id, read=False).order_by(Notification.created_at.desc()).limit(5).all()

    # Generate personalized wellness tips
    mood_analysis = analyze_mood_patterns(user.id)
    wellness_tips = generate_wellness_tips(mood_analysis)

    return render_template('dashboard.html', 
                         user=user, 
                         entries=entries, 
                         delete_form=delete_form,
                         most_common_mood=most_common_mood,
                         total_entries=total_entries,
                         selected_month=month_str,
                         selected_date=date_str,
                         start_date=start_date_str,
                         end_date=end_date_str,
                         filter_type=filter_type,
                         overall_average=overall_average,
                         best_day=best_day,
                         worst_day=worst_day,
                         daily_averages=daily_averages,
                         wellness_tips=wellness_tips,
                         mood_analysis=mood_analysis,
                         notifications=notifications)

@app.route('/add_entry', methods=['GET', 'POST'])
def add_entry():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    form = WellnessEntryForm()
    if form.validate_on_submit():
        # Determine which mood to use: custom_mood if provided, otherwise selected mood
        selected_mood = form.custom_mood.data.strip() if form.custom_mood.data and form.custom_mood.data.strip() else form.mood.data
        
        # Validate that at least one mood is provided
        if not selected_mood:
            flash('Please select a mood from the dropdown or enter a custom mood.', 'danger')
            return render_template('add_entry.html', form=form)
        
        # Validate intensity value
        intensity = form.intensity.data
        if intensity is None or intensity < 1 or intensity > 5:
            flash('Invalid intensity value. Please select a value between 1 and 5.', 'danger')
            return render_template('add_entry.html', form=form)
        
        # Create new wellness entry
        entry = WellnessEntry(
            user_id=session['user_id'],
            mood=selected_mood,
            intensity=intensity,
            notes=form.notes.data
        )
        db.session.add(entry)
        db.session.commit()
        flash('Wellness entry saved successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('add_entry.html', form=form)

@app.route('/entry/<int:entry_id>/edit', methods=['GET', 'POST'])
def edit_entry(entry_id: int):
    if not session.get('user_id'):
        return redirect(url_for('login'))

    entry = WellnessEntry.query.get_or_404(entry_id)
    if entry.user_id != session['user_id']:
        abort(403)

    form = WellnessEntryForm(obj=entry)
    if form.validate_on_submit():
        # Determine which mood to use: custom_mood if provided, otherwise selected mood
        selected_mood = form.custom_mood.data.strip() if form.custom_mood.data and form.custom_mood.data.strip() else form.mood.data
        
        # Validate that at least one mood is provided
        if not selected_mood:
            flash('Please select a mood from the dropdown or enter a custom mood.', 'danger')
            return render_template('edit_entry.html', form=form, entry=entry)
        
        # Validate intensity value
        intensity = form.intensity.data
        if intensity is None or intensity < 1 or intensity > 5:
            flash('Invalid intensity value. Please select a value between 1 and 5.', 'danger')
            return render_template('edit_entry.html', form=form, entry=entry)
        
        entry.mood = selected_mood
        entry.intensity = intensity
        entry.notes = form.notes.data
        db.session.commit()
        flash('Wellness entry updated.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('edit_entry.html', form=form, entry=entry)

@app.route('/entry/<int:entry_id>/delete', methods=['POST'])
def delete_entry(entry_id: int):
    if not session.get('user_id'):
        return redirect(url_for('login'))

    entry = WellnessEntry.query.get_or_404(entry_id)
    if entry.user_id != session['user_id']:
        abort(403)

    form = DeleteEntryForm()
    if form.validate_on_submit():
        db.session.delete(entry)
        db.session.commit()
        flash('Entry deleted.', 'info')
    else:
        flash('Invalid delete request.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/api/mood_data')
def mood_data():
    if not session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    # Support custom date range filtering
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    month_str = request.args.get('month') or datetime.utcnow().strftime('%Y-%m')
    date_str = request.args.get('date') or ''

    # Determine date range to use (same logic as dashboard)
    filter_start = None
    filter_end = None
    
    if start_date_str and end_date_str:
        try:
            filter_start = datetime.strptime(start_date_str, '%Y-%m-%d')
            filter_end = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
        except Exception:
            pass
    
    if not filter_start and date_str:
        try:
            y, m, d = [int(p) for p in date_str.split('-')]
            filter_start = datetime(y, m, d)
            filter_end = filter_start + timedelta(days=1)
        except Exception:
            pass
    
    if not filter_start:
        try:
            year, month = [int(part) for part in month_str.split('-')]
            filter_start = datetime(year, month, 1)
            if month == 12:
                filter_end = datetime(year + 1, 1, 1)
            else:
                filter_end = datetime(year, month + 1, 1)
        except Exception:
            filter_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if filter_start.month == 12:
                filter_end = datetime(filter_start.year + 1, 1, 1)
            else:
                filter_end = datetime(filter_start.year, filter_start.month + 1, 1)

    # Get mood distribution and entries for timeline
    mood_counts = db.session.query(WellnessEntry.mood, db.func.count(WellnessEntry.id)).filter(
        WellnessEntry.user_id == user_id,
        WellnessEntry.created_at >= filter_start,
        WellnessEntry.created_at < filter_end
    ).group_by(WellnessEntry.mood).all()
    
    month_entries = WellnessEntry.query.filter(
        WellnessEntry.user_id == user_id,
        WellnessEntry.created_at >= filter_start,
        WellnessEntry.created_at < filter_end
    ).order_by(WellnessEntry.created_at.asc()).all()
    
    # Prepare data for charts
    mood_distribution = {
        'labels': [mood[0] for mood in mood_counts],
        'data': [mood[1] for mood in mood_counts]
    }
    
    # Create complete timeline with all days for the selected range
    all_dates = []
    if start_date_str and end_date_str:
        # Custom date range - include all days in range
        current_date = filter_start.date()
        end_date = filter_end.date()
        while current_date < end_date:
            all_dates.append(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)
    elif date_str:
        # Single date
        all_dates = [filter_start.strftime('%Y-%m-%d')]
    else:
        # Month view - all days in month
        day_cursor = filter_start
        while day_cursor < filter_end:
            all_dates.append(day_cursor.strftime('%Y-%m-%d'))
            day_cursor = day_cursor + timedelta(days=1)
    
    # Get all unique moods from user's entries (not just recent ones)
    all_moods = db.session.query(WellnessEntry.mood).filter_by(user_id=user_id).distinct().all()
    all_moods = [mood[0] for mood in all_moods]
    
    # Mood scoring system (same as in analyze_mood_patterns)
    mood_scores = {
        'Happy': 5, 'Excited': 5, 'Grateful': 4, 'Proud': 4, 'Hopeful': 4, 'Content': 4,
        'Calm': 3, 'Tired': 2, 'Confused': 2,
        'Sad': 1, 'Anxious': 1, 'Frustrated': 1, 'Lonely': 1, 'Overwhelmed': 1
    }
    
    # Create mood score timeline with only actual entry dates (no fill-in for missing days)
    # Get the latest entry for each date (in case of multiple entries per day)
    # Since entries are ordered by created_at.asc(), later entries will overwrite earlier ones for the same date
    mood_data_by_date = {}
    for entry in month_entries:
        date_str = entry.created_at.strftime('%Y-%m-%d')
        # If multiple entries on same day, use the latest one (last one processed wins)
        mood_data_by_date[date_str] = {
            'intensity': entry.intensity,
            'mood': entry.mood
        }
    
    # Only include dates that have actual entries (no fill-in for missing days)
    entry_dates = sorted(mood_data_by_date.keys())
    mood_scores = []
    mood_types = []
    
    for date in entry_dates:
        mood_scores.append(mood_data_by_date[date]['intensity'])
        mood_types.append(mood_data_by_date[date]['mood'])
    
    # Create timeline data structure - only dates with actual entries
    timeline_data = {
        'dates': entry_dates,
        'mood_scores': mood_scores,
        'mood_types': mood_types
    }
    
    return jsonify({
        'mood_distribution': mood_distribution,
        'timeline': timeline_data
    })

@app.route('/export/csv')
def export_csv():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    entries = WellnessEntry.query.filter_by(user_id=user.id).order_by(WellnessEntry.created_at.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['date', 'mood', 'notes'])
    for e in entries:
        writer.writerow([e.created_at.strftime('%Y-%m-%d %H:%M:%S'), e.mood, e.notes or ''])

    csv_data = output.getvalue()
    output.close()

    response = make_response(csv_data)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=wellness_entries.csv'
    return response

# -------------------- Reminder management --------------------
@app.route('/reminders', methods=['GET', 'POST'])
def reminders():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    setting = ReminderSetting.query.filter_by(user_id=user.id).first()
    if not setting:
        setting = ReminderSetting(user_id=user.id, enabled=False, reminder_time_utc='18:00', channel='in_app')
        db.session.add(setting)
        db.session.commit()
    
    # Create form with saved time (stored in 12-hour format for simplicity)
    form = ReminderForm(obj=setting)
    # The form will automatically populate with the saved time from the database
    if form.validate_on_submit():
        setting.enabled = form.enabled.data or False
        setting.channel = 'in_app'  # Force in-app reminders only
        
        # Handle time input from dropdowns - construct 12-hour format
        hour = request.form.get('reminder_hour', '').strip()
        minute = request.form.get('reminder_minute', '').strip()
        ampm = request.form.get('reminder_ampm', '').strip()
        
        if hour and minute and ampm:
            # Construct time string in 12-hour format like "3:30 PM"
            try:
                hour_int = int(hour)
                minute_int = int(minute)
                
                # Validate hour and minute ranges
                if 1 <= hour_int <= 12 and 0 <= minute_int <= 59:
                    time_string = f"{hour_int}:{minute_int:02d} {ampm}"
                    setting.reminder_time_utc = time_string
                    print(f"User {user.username}: Saved reminder time as: {time_string}")
                else:
                    setting.reminder_time_utc = None
                    flash('Invalid time selected. Please choose a valid hour and minute.', 'danger')
            except ValueError:
                setting.reminder_time_utc = None
                flash('Invalid time format. Please try again.', 'danger')
        else:
            setting.reminder_time_utc = None
        
        db.session.commit()
        
        # Reschedule the reminder job for this user
        try:
            # Remove existing job if it exists
            job_id = f'reminder_{user.id}'
            try:
                scheduler.remove_job(job_id)
            except:
                pass  # Job doesn't exist, that's fine
            
            # Schedule new job if reminder is enabled and time is set
            if setting.enabled and setting.reminder_time_utc:
                reminder_time = datetime.strptime(setting.reminder_time_utc.strip(), '%I:%M %p')
                scheduler.add_job(
                    func=send_reminder_for_user,
                    trigger='cron',
                    hour=reminder_time.hour,
                    minute=reminder_time.minute,
                    second=0,
                    args=[user.id],
                    id=job_id,
                    replace_existing=True
                )
                print(f"Rescheduled reminder for user {user.username} at {setting.reminder_time_utc}")
        except Exception as e:
            print(f"Error rescheduling reminder: {e}")
        
        flash('In-app reminder settings saved successfully!', 'success')
        return redirect(url_for('reminders'))
    return render_template('reminders.html', form=form, user=user, setting=setting)

@app.route('/debug/time', methods=['POST'])
def debug_time():
    """Debug endpoint to see what time values are being received."""
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    data = request.form.to_dict()
    print("🔍 DEBUG: Form data received:")
    for key, value in data.items():
        print(f"  {key}: {value}")
    
    return jsonify({
        'status': 'success',
        'received_data': data,
        'current_utc_time': datetime.utcnow().strftime('%H:%M'),
        'user_timezone_offset': data.get('timezone_offset', 'not_provided')
    })

@app.route('/debug/reminders')
def debug_reminders():
    """Debug endpoint to check reminder settings and current time."""
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    setting = ReminderSetting.query.filter_by(user_id=user.id).first()
    
    now = datetime.now()
    current_time_formats = [
        now.strftime('%I:%M %p').lstrip('0'),  # "3:30 PM"
        now.strftime('%I:%M %p'),              # "03:30 PM"
        now.strftime('%I:%M %p').replace(' 0', ' '),  # "3:30 PM"
    ]
    
    return jsonify({
        'current_time': now.strftime('%H:%M'),
        'current_12h_formats': current_time_formats,
        'reminder_setting': {
            'enabled': setting.enabled if setting else False,
            'reminder_time': setting.reminder_time_utc if setting else None,
            'channel': setting.channel if setting else None
        },
        'scheduler_running': scheduler.running,
        'user_id': user.id
    })

@app.route('/notifications/read/<int:notification_id>', methods=['POST'])
def read_notification(notification_id: int):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    n = Notification.query.get_or_404(notification_id)
    if n.user_id != session['user_id']:
        abort(403)
    n.read = True
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/notifications/mark-all-read', methods=['POST'])
def mark_all_notifications_read():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    # Check CSRF token
    from flask_wtf.csrf import validate_csrf
    try:
        validate_csrf(request.form.get('csrf_token'))
    except:
        flash('CSRF token is missing or invalid.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Mark all unread notifications for the current user as read (optimized)
    user_id = session['user_id']
    
    # Use bulk update for better performance
    updated_count = Notification.query.filter_by(user_id=user_id, read=False).update({
        'read': True
    })
    
    db.session.commit()
    
    if updated_count > 0:
        flash(f'Marked {updated_count} notifications as read.', 'success')
    else:
        flash('No unread notifications to mark.', 'info')
    
    return redirect(url_for('dashboard'))

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        # Verify current password
        if not check_password_hash(user.password_hash, form.current_password.data):
            flash('Current password is incorrect.', 'danger')
            return render_template('change_password.html', form=form)
        
        # Update password
        user.password_hash = generate_password_hash(form.new_password.data)
        db.session.commit()
        flash('Password changed successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('change_password.html', form=form)

@app.route('/delete_account', methods=['GET', 'POST'])
def delete_account():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    form = DeleteAccountForm()
    
    if form.validate_on_submit():
        # Security checks
        if form.confirmation_text.data != 'DELETE':
            flash('You must type "DELETE" exactly to confirm account deletion.', 'danger')
            return render_template('delete_account.html', form=form, user=user)
        
        if not check_password_hash(user.password_hash, form.current_password.data):
            flash('Current password is incorrect.', 'danger')
            return render_template('delete_account.html', form=form, user=user)
        
        # Get counts for confirmation message
        entries_count = WellnessEntry.query.filter_by(user_id=user.id).count()
        notifications_count = Notification.query.filter_by(user_id=user.id).count()
        
        # Delete all user data in correct order (respecting foreign key constraints)
        try:
            # Delete notifications first
            Notification.query.filter_by(user_id=user.id).delete()
            
            # Delete reminder settings
            ReminderSetting.query.filter_by(user_id=user.id).delete()
            
            # Delete wellness entries
            WellnessEntry.query.filter_by(user_id=user.id).delete()
            
            # Finally delete the user
            db.session.delete(user)
            db.session.commit()
            
            # Clear session
            session.clear()
            
            flash(f'Account permanently deleted. Removed {entries_count} wellness entries and {notifications_count} notifications.', 'success')
            return redirect(url_for('home'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while deleting your account. Please try again.', 'danger')
            return render_template('delete_account.html', form=form, user=user)
    
    return render_template('delete_account.html', form=form, user=user)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    form = ProfileForm(obj=user)
    
    # Calculate streak and statistics
    entries = WellnessEntry.query.filter_by(user_id=user.id).order_by(WellnessEntry.created_at.desc()).all()
    
    # Calculate current streak
    current_streak = 0
    if entries:
        # Get unique dates when user logged entries
        entry_dates = set()
        for entry in entries:
            entry_dates.add(entry.created_at.date())
        
        # Sort dates and calculate streak
        sorted_dates = sorted(entry_dates, reverse=True)
        today = datetime.utcnow().date()
        
        # Check if user logged today or yesterday
        if today in sorted_dates:
            current_date = today
        elif (today - timedelta(days=1)) in sorted_dates:
            current_date = today - timedelta(days=1)
        else:
            current_date = None
        
        # Count consecutive days
        if current_date:
            current_streak = 1
            for i in range(1, len(sorted_dates)):
                if sorted_dates[i] == current_date - timedelta(days=i):
                    current_streak += 1
                else:
                    break
    
    # Calculate total statistics
    total_entries = len(entries)
    days_with_entries = len(set(entry.created_at.date() for entry in entries))
    
    # Get most recent entry
    most_recent_entry = entries[0] if entries else None
    
    # Get reminder settings
    reminder_setting = ReminderSetting.query.filter_by(user_id=user.id).first()
    
    if form.validate_on_submit():
        # Check if username/email already exists (excluding current user)
        existing_user = User.query.filter(
            User.username == form.username.data,
            User.id != user.id
        ).first()
        if existing_user:
            flash('Username already taken. Please choose another.', 'danger')
            return render_template('profile.html', form=form, user=user, 
                                 current_streak=current_streak, total_entries=total_entries,
                                 days_with_entries=days_with_entries, most_recent_entry=most_recent_entry,
                                 reminder_setting=reminder_setting)
        
        existing_email = User.query.filter(
            User.email == form.email.data,
            User.id != user.id
        ).first()
        if existing_email:
            flash('Email already registered. Please use another email.', 'danger')
            return render_template('profile.html', form=form, user=user,
                                 current_streak=current_streak, total_entries=total_entries,
                                 days_with_entries=days_with_entries, most_recent_entry=most_recent_entry,
                                 reminder_setting=reminder_setting)
        
        # Update user profile
        user.username = form.username.data
        user.email = form.email.data
        db.session.commit()
        
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('profile.html', form=form, user=user,
                         current_streak=current_streak, total_entries=total_entries,
                         days_with_entries=days_with_entries, most_recent_entry=most_recent_entry,
                         reminder_setting=reminder_setting)

# ==================== ADMIN PANEL ROUTES ====================

# Helper functions for login rate limiting
def get_client_ip():
    """Get the client's IP address from request"""
    if request.headers.get('X-Forwarded-For'):
        # Behind proxy
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP')
    else:
        ip = request.remote_addr
    return ip

def check_if_locked(ip_address):
    """Check if IP is currently locked out"""
    attempt = LoginAttempt.query.filter_by(ip_address=ip_address).first()
    
    if not attempt:
        return False
    
    if attempt.locked_until:
        # Check if lockout has expired
        if datetime.utcnow() < attempt.locked_until:
            # Still locked
            return True
        else:
            # Lockout expired, reset
            attempt.attempt_count = 0
            attempt.locked_until = None
            db.session.commit()
            return False
    
    return False

def get_lockout_info(ip_address):
    """Get remaining lockout time in minutes"""
    attempt = LoginAttempt.query.filter_by(ip_address=ip_address).first()
    
    if not attempt or not attempt.locked_until:
        return None
    
    if datetime.utcnow() < attempt.locked_until:
        remaining = attempt.locked_until - datetime.utcnow()
        minutes_remaining = int(remaining.total_seconds() / 60) + 1
        return minutes_remaining
    
    return None

def record_failed_attempt(ip_address):
    """Record a failed login attempt and return attempts remaining"""
    attempt = LoginAttempt.query.filter_by(ip_address=ip_address).first()
    
    if not attempt:
        # First failed attempt
        attempt = LoginAttempt(ip_address=ip_address, attempt_count=1)
        db.session.add(attempt)
        db.session.commit()
        return MAX_LOGIN_ATTEMPTS - 1  # 2 remaining
    
    # Increment counter
    attempt.attempt_count += 1
    attempt.last_attempt_time = datetime.utcnow()
    
    # Check if should be locked
    if attempt.attempt_count >= MAX_LOGIN_ATTEMPTS:
        attempt.locked_until = datetime.utcnow() + timedelta(seconds=LOCKOUT_DURATION_SECONDS)
        db.session.commit()
        return 0  # Locked
    
    db.session.commit()
    return MAX_LOGIN_ATTEMPTS - attempt.attempt_count

def reset_login_attempts(ip_address):
    """Reset attempts counter on successful login"""
    attempt = LoginAttempt.query.filter_by(ip_address=ip_address).first()
    
    if attempt:
        attempt.attempt_count = 0
        attempt.locked_until = None
        attempt.last_attempt_time = datetime.utcnow()
        db.session.commit()

def get_current_attempts(ip_address):
    """Get current attempt count for displaying"""
    attempt = LoginAttempt.query.filter_by(ip_address=ip_address).first()
    
    if not attempt:
        return 0
    
    return attempt.attempt_count

# Helper decorator for admin-only routes
from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in to access admin panel.', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin Login
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    # Get client IP
    ip = get_client_ip()
    
    # Check if locked out
    if check_if_locked(ip):
        minutes_remaining = get_lockout_info(ip)
        flash(f'🔒 Too many failed login attempts. Account locked for {minutes_remaining} minutes.', 'error')
        return render_template('admin/admin_login.html', 
                             locked=True, 
                             minutes_remaining=minutes_remaining)
    
    if request.method == 'POST':
        # Check CSRF token manually
        from flask_wtf.csrf import validate_csrf
        try:
            validate_csrf(request.form.get('csrf_token'))
        except:
            flash('CSRF token is missing or invalid.', 'danger')
            return render_template('admin/admin_login.html')
        
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Check credentials
        admin = Admin.query.filter_by(username=username).first()
        
        if admin and admin.check_password(password):
            # Successful login - reset attempts
            reset_login_attempts(ip)
            session['admin_id'] = admin.id
            session['admin_username'] = admin.username
            admin.last_login = datetime.utcnow()
            db.session.commit()
            flash('Welcome to admin panel!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            # Failed login - record attempt
            attempts_remaining = record_failed_attempt(ip)
            
            if attempts_remaining == 0:
                flash(f'🔒 Too many failed attempts. Account locked for {LOCKOUT_DURATION_MINUTES} minutes.', 'error')
                return render_template('admin/admin_login.html', 
                                     locked=True, 
                                     minutes_remaining=LOCKOUT_DURATION_MINUTES)
            else:
                flash(f'❌ Invalid credentials. {attempts_remaining} attempt{"s" if attempts_remaining != 1 else ""} remaining.', 'warning')
                return render_template('admin/admin_login.html', 
                                     attempts_remaining=attempts_remaining)
    
    # GET request - check current status
    current_attempts = get_current_attempts(ip)
    attempts_remaining = MAX_LOGIN_ATTEMPTS - current_attempts if current_attempts > 0 else None
    
    return render_template('admin/admin_login.html', 
                         attempts_remaining=attempts_remaining)

# Admin Dashboard
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Statistics
    total_messages = ContactMessage.query.count()
    unread_messages = ContactMessage.query.filter_by(is_read=False).count()
    total_users = User.query.count()
    today = datetime.utcnow().date()
    today_messages = ContactMessage.query.filter(
        db.func.date(ContactMessage.date_submitted) == today
    ).count()
    
    # Recent messages
    recent_messages = ContactMessage.query.order_by(
        ContactMessage.date_submitted.desc()
    ).limit(5).all()
    
    # Chart data - messages per day (last 7 days)
    from datetime import timedelta
    chart_data = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        count = ContactMessage.query.filter(
            db.func.date(ContactMessage.date_submitted) == date
        ).count()
        chart_data.append({
            'date': date.strftime('%b %d'),
            'count': count
        })
    
    return render_template('admin/admin_dashboard.html',
                         total_messages=total_messages,
                         unread_messages=unread_messages,
                         total_users=total_users,
                         today_messages=today_messages,
                         recent_messages=recent_messages,
                         chart_data=chart_data)

# Messages List
@app.route('/admin/messages')
@admin_required
def admin_messages():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    search = request.args.get('search', '')
    
    query = ContactMessage.query
    
    if status_filter == 'unread':
        query = query.filter_by(is_read=False)
    elif status_filter == 'read':
        query = query.filter_by(is_read=True)
    
    if search:
        query = query.filter(
            (ContactMessage.name.contains(search)) |
            (ContactMessage.email.contains(search)) |
            (ContactMessage.subject.contains(search))
        )
    
    messages = query.order_by(ContactMessage.date_submitted.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    
    return render_template('admin/admin_messages.html', messages=messages)

# Message Detail
@app.route('/admin/messages/<int:id>')
@admin_required
def admin_message_detail(id):
    message = ContactMessage.query.get_or_404(id)
    
    # Mark as read
    if not message.is_read:
        message.is_read = True
        message.read_at = datetime.utcnow()
        db.session.commit()
    
    return render_template('admin/admin_message_detail.html', message=message)

# Mark as Read/Unread
@app.route('/admin/messages/<int:id>/toggle-read', methods=['POST'])
@admin_required
def toggle_message_read(id):
    # Validate CSRF token
    from flask_wtf.csrf import validate_csrf
    try:
        validate_csrf(request.form.get('csrf_token'))
    except:
        flash('CSRF token is missing or invalid.', 'danger')
        return redirect(request.referrer or url_for('admin_messages'))
    
    message = ContactMessage.query.get_or_404(id)
    message.is_read = not message.is_read
    message.read_at = datetime.utcnow() if message.is_read else None
    db.session.commit()
    flash('Message status updated.', 'success')
    return redirect(request.referrer or url_for('admin_messages'))

# Delete Message
@app.route('/admin/messages/<int:id>/delete', methods=['POST'])
@admin_required
def delete_message(id):
    # Validate CSRF token
    from flask_wtf.csrf import validate_csrf
    try:
        validate_csrf(request.form.get('csrf_token'))
    except:
        flash('CSRF token is missing or invalid.', 'danger')
        return redirect(request.referrer or url_for('admin_messages'))
    
    message = ContactMessage.query.get_or_404(id)
    db.session.delete(message)
    db.session.commit()
    flash('Message deleted successfully.', 'success')
    return redirect(url_for('admin_messages'))

# User Management
@app.route('/admin/users')
@admin_required
def admin_users():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    query = User.query
    
    if search:
        query = query.filter(
            (User.username.contains(search)) |
            (User.email.contains(search))
        )
    
    users = query.order_by(User.id.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Calculate user activity status
    now = datetime.utcnow()
    user_statuses = {}
    
    for user in users.items:
        # Get the latest wellness entry
        latest_entry = WellnessEntry.query.filter_by(user_id=user.id).order_by(
            WellnessEntry.created_at.desc()
        ).first()
        
        if latest_entry:
            # Calculate days since last entry
            days_since_entry = (now - latest_entry.created_at).days
            
            if days_since_entry <= 1:  # Within 24 hours
                user_statuses[user.id] = {
                    'status': 'active',
                    'badge_type': 'success',
                    'badge_text': 'ACTIVE'
                }
            else:
                user_statuses[user.id] = {
                    'status': 'inactive',
                    'badge_type': 'warning' if days_since_entry <= 7 else 'danger',
                    'badge_text': f'INACTIVE: {days_since_entry} days'
                }
        else:
            # No entries ever
            user_statuses[user.id] = {
                'status': 'inactive',
                'badge_type': 'danger',
                'badge_text': 'INACTIVE: since signup'
            }
    
    return render_template('admin/admin_users.html', users=users, user_statuses=user_statuses)

# Admin Logout
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('admin_login'))

# Admin Change Password
@app.route('/admin/change-password', methods=['GET', 'POST'])
@admin_required
def admin_change_password():
    admin = Admin.query.get(session['admin_id'])
    form = AdminChangePasswordForm()
    
    if form.validate_on_submit():
        # Verify current password
        if not admin.check_password(form.current_password.data):
            flash('Current password is incorrect.', 'danger')
            return render_template('admin/admin_change_password.html', form=form)
        
        # Check if new password is the same as current password
        if admin.check_password(form.new_password.data):
            flash('New password must be different from your current password.', 'danger')
            return render_template('admin/admin_change_password.html', form=form)
        
        # Validate password requirements
        if len(form.new_password.data) < 8:
            flash('New password must be at least 8 characters long.', 'danger')
            return render_template('admin/admin_change_password.html', form=form)
        
        # Update password
        admin.set_password(form.new_password.data)
        db.session.commit()
        
        flash('Password changed successfully! Please log in again with your new password.', 'success')
        
        # Clear admin session to force re-login with new password
        session.pop('admin_id', None)
        session.pop('admin_username', None)
        
        return redirect(url_for('admin_login'))
    
    return render_template('admin/admin_change_password.html', form=form)


# Create admin user if none exists (for development)
def create_admin_if_not_exists():
    with app.app_context():
        admin = Admin.query.first()
        if not admin:
            admin = Admin(
                username='admin',
                email='admin@mindspace.com'
            )
            admin.set_password('admin123')  # Change this in production!
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin user created: username='admin', password='admin123'")
            print("⚠️  WARNING: Change admin credentials in production!")

if __name__ == '__main__':
    create_admin_if_not_exists()
    app.run(debug=True)