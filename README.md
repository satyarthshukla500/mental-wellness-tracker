# 🧠 Mental Wellness Tracker

A full-stack web application for tracking daily mood and mental wellness, built with Flask, SQLAlchemy, and Python. Developed as a group project at Avantika University by **Team Voidwalkers**.

---

## 📌 About

Mental Wellness Tracker helps users log their daily mood, monitor emotional patterns over time, and receive personalized wellness tips based on their history. It features a secure user system, an admin panel, automated reminders, and detailed analytics — all wrapped in a clean, responsive interface.

---

## ✨ Features

- **Mood Logging** — Log daily mood entries with intensity ratings (1–5) and personal notes
- **Analytics Dashboard** — Visual charts for mood trends, best/worst days, and monthly breakdowns
- **Personalized Wellness Tips** — AI-style tips generated based on your mood patterns
- **Daily Reminders** — Configurable in-app reminders with exact-time scheduling via APScheduler
- **User Authentication** — Secure registration, login, and session management
- **Admin Panel** — Full admin dashboard with user management, contact messages, and login rate limiting
- **CSV Export** — Export all mood entries as a downloadable CSV file
- **CSRF Protection** — All forms protected with Flask-WTF CSRF tokens
- **Password Security** — Passwords hashed using Werkzeug's security utilities
- **Responsive Design** — Works on desktop and mobile browsers

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, Flask |
| Database | SQLAlchemy (SQLite locally, PostgreSQL on production) |
| Forms | Flask-WTF, WTForms |
| Scheduling | APScheduler |
| Frontend | HTML5, CSS3, JavaScript, Jinja2 Templates |
| Security | CSRF Protection, Password Hashing, Session Management, Login Rate Limiting |
| Email | Python smtplib (SMTP) |

---

## 📁 Project Structure

```
mental-wellness-tracker/
├── app.py               # Main Flask application & all route handlers
├── models.py            # SQLAlchemy database models
├── forms.py             # WTForms form definitions
├── config.py            # App configuration
├── requirements.txt     # Python dependencies
├── static/              # CSS, JS, images
│   ├── css/
│   ├── js/
│   └── images/
└── templates/           # Jinja2 HTML templates
    ├── admin/           # Admin panel templates
    ├── dashboard.html
    ├── login.html
    ├── register.html
    └── ...
```

---

## 🚀 Getting Started (Local Setup)

### Prerequisites
- Python 3.10+
- pip

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/satyarthshukla500/mental-wellness-tracker.git
cd mental-wellness-tracker

# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py
```

The app will be live at `http://127.0.0.1:5000`

---

## 🔐 Environment Variables (for Production)

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask secret key for session security |
| `DATABASE_URL` | PostgreSQL connection string |
| `SMTP_HOST` | SMTP server for email reminders |
| `SMTP_USER` | Email address for sending reminders |
| `SMTP_PASSWORD` | Email password |
| `SMTP_PORT` | SMTP port (default: 587) |

---

## 👥 Team

**Team Voidwalkers** — Avantika University, Ujjain

- Satyarth Shukla
- Somya
- Tanishq

**Subject:** Web Technologies Lab (Flask Project)  
**Grade:** 84% — Prof. Dinesh Patel

---

## 📄 License

This project was built for academic purposes. Feel free to explore the code and use it as a reference.
