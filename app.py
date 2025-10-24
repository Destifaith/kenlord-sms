from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os
import pandas as pd
import requests
from werkzeug.utils import secure_filename
from flask_login import (
    LoginManager, login_user, login_required,
    logout_user, current_user
)
from models import db, Category, Contact, User

# Load environment variables
load_dotenv()

app = Flask(__name__)

# App configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or "dev_secret_key"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
db.init_app(app)

# --- ✅ Initialize Login Manager ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Redirects unauthorized users
login_manager.login_message_category = 'info'

# --- Flask-Login user loader ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def home():
    return "<h2>School SMS App is Running 🚀</h2>"


# --- Dashboard ---
@app.route('/dashboard')
@login_required
def dashboard():
    categories = Category.query.all()
    return render_template('dashboard.html', categories=categories)


# --- Category Routes ---
@app.route('/add_category', methods=['POST'])
@login_required
def add_category():
    name = request.form['name']
    if name.strip() == "":
        flash("Category name cannot be empty!", "danger")
        return redirect(url_for('dashboard'))
    if Category.query.filter_by(name=name).first():
        flash("Category already exists!", "warning")
        return redirect(url_for('dashboard'))

    new_cat = Category(name=name)
    db.session.add(new_cat)
    db.session.commit()
    flash("Category added successfully!", "success")
    return redirect(url_for('dashboard'))


@app.route('/delete_category/<int:id>', methods=['POST'])
@login_required
def delete_category(id):
    category = Category.query.get(id)
    if category:
        db.session.delete(category)
        db.session.commit()
        flash("Category deleted successfully!", "success")
    else:
        flash("Category not found!", "danger")
    return redirect(url_for('dashboard'))


# --- Contacts ---
@app.route('/contacts/<int:category_id>')
@login_required
def view_contacts(category_id):
    category = Category.query.get_or_404(category_id)
    return render_template('contacts.html', category=category)


@app.route('/upload_contacts/<int:category_id>', methods=['POST'])
@login_required
def upload_contacts(category_id):
    category = Category.query.get_or_404(category_id)
    file = request.files['file']

    if not file:
        flash("No file selected!", "danger")
        return redirect(url_for('view_contacts', category_id=category_id))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        df = pd.read_excel(filepath)
        for _, row in df.iterrows():
            if 'Phone' in df.columns:
                phone = str(row['Phone'])
                name = row['Name'] if 'Name' in df.columns else None
                new_contact = Contact(name=name, phone=phone, category_id=category.id)
                db.session.add(new_contact)
        db.session.commit()
        flash("Contacts uploaded successfully!", "success")
    except Exception as e:
        flash(f"Error uploading contacts: {e}", "danger")

    return redirect(url_for('view_contacts', category_id=category_id))


@app.route('/add_contact/<int:category_id>', methods=['POST'])
@login_required
def add_contact(category_id):
    category = Category.query.get_or_404(category_id)
    name = request.form.get('name')
    phone = request.form.get('phone')

    if not phone.strip():
        flash("Phone number is required!", "danger")
        return redirect(url_for('view_contacts', category_id=category_id))

    new_contact = Contact(name=name, phone=phone, category_id=category.id)
    db.session.add(new_contact)
    db.session.commit()
    flash("Contact added successfully!", "success")
    return redirect(url_for('view_contacts', category_id=category_id))


@app.route('/edit_contact/<int:contact_id>', methods=['POST'])
@login_required
def edit_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    contact.name = request.form.get('name')
    contact.phone = request.form.get('phone')
    db.session.commit()
    flash("Contact updated successfully!", "success")
    return redirect(url_for('view_contacts', category_id=contact.category_id))


@app.route('/delete_contact/<int:contact_id>', methods=['POST'])
@login_required
def delete_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    category_id = contact.category_id
    db.session.delete(contact)
    db.session.commit()
    flash("Contact deleted successfully!", "success")
    return redirect(url_for('view_contacts', category_id=category_id))


# --- Send SMS ---
@app.route('/send_sms/<int:category_id>', methods=['POST'])
@login_required
def send_sms(category_id):
    category = Category.query.get_or_404(category_id)
    message = request.form.get('message')
    sender_id = os.getenv("SENDER_ID")
    api_key = os.getenv("MNOTIFY_API_KEY")

    if not message or not message.strip():
        flash("Message cannot be empty!", "danger")
        return redirect(url_for('view_contacts', category_id=category.id))

    contacts = [c.phone for c in category.contacts]
    if not contacts:
        flash("No contacts found in this category!", "danger")
        return redirect(url_for('view_contacts', category_id=category.id))

    url = "https://api.mnotify.com/api/sms/quick"
    payload = {
        "key": api_key,
        "recipient": contacts,
        "sender": sender_id,
        "message": message
    }

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            flash("Messages sent successfully!", "success")
        else:
            flash(f"Failed to send SMS: {response.text}", "danger")
    except Exception as e:
        flash(f"Error sending SMS: {e}", "danger")

    return redirect(url_for('view_contacts', category_id=category.id))


# --- Login & Logout ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('login'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
