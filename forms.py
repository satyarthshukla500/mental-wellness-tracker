from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField, BooleanField, IntegerField
from wtforms.validators import DataRequired, Email, Length, EqualTo, NumberRange

class RegistrationForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField("Register")

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")

class WellnessEntryForm(FlaskForm):
    mood = SelectField("How are you feeling?", 
                      choices=[
                          ('', 'Select a mood...'),
                          ('Happy', 'Happy 😊'),
                          ('Sad', 'Sad 😢'),
                          ('Anxious', 'Anxious 😰'),
                          ('Calm', 'Calm 😌'),
                          ('Excited', 'Excited 🤩'),
                          ('Tired', 'Tired 😴'),
                          ('Frustrated', 'Frustrated 😤'),
                          ('Grateful', 'Grateful 🙏'),
                          ('Confused', 'Confused 🤔'),
                          ('Proud', 'Proud 🏆'),
                          ('Lonely', 'Lonely 😔'),
                          ('Hopeful', 'Hopeful 🌟'),
                          ('Overwhelmed', 'Overwhelmed 😵'),
                          ('Content', 'Content 😊')
                      ],
                      validators=[])  # Remove DataRequired since custom_mood can be used instead
    custom_mood = StringField("Or enter your own mood:", 
                             render_kw={"placeholder": "e.g., Nostalgic, Determined, Peaceful..."})
    intensity = IntegerField("Intensity (1-5)", 
                           validators=[DataRequired(message="Please select an intensity level"), 
                                     NumberRange(min=1, max=5, message="Intensity must be between 1 and 5")],
                           default=3,
                           render_kw={"min": 1, "max": 5, "placeholder": "1 (low) to 5 (high)", "required": True})
    notes = TextAreaField("Notes (optional)", 
                          render_kw={"rows": 4, "placeholder": "How was your day? What's on your mind?"})
    submit = SubmitField("Save Entry")

class DeleteEntryForm(FlaskForm):
    submit = SubmitField("Delete")

class ReminderForm(FlaskForm):
    enabled = BooleanField("Enable daily reminder")
    channel = SelectField("Delivery method", choices=[('in_app', 'In-app'), ('email', 'Email')])
    reminder_time_utc = StringField("Reminder time")
    submit = SubmitField("Save Reminders")

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField("Confirm New Password", validators=[DataRequired(), EqualTo('new_password', message='Passwords must match')])
    submit = SubmitField("Change Password")

class DeleteAccountForm(FlaskForm):
    confirmation_text = StringField("Type 'DELETE' to confirm", validators=[DataRequired()])
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    submit = SubmitField("Permanently Delete My Account")

class ProfileForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Update Profile")

class AdminChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField("Confirm New Password", validators=[DataRequired(), EqualTo('new_password', message='Passwords must match')])
    submit = SubmitField("Change Password")