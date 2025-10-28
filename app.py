from flask import Flask, render_template, request, redirect, url_for, flash
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

# --- Configuration ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or "dev_secret_key"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Initialize database ---
db.init_app(app)

# --- Login Manager Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ===============================================================
# 🔹 Helper Function — Fetch SMS Balance from MNotify
# ===============================================================
def get_sms_balance():
    """Fetch SMS balance and wallet info from MNotify"""
    api_key = os.getenv("MNOTIFY_API_KEY")
    url = f"https://api.mnotify.com/api/balance/sms?key={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                "balance": data.get("balance", 0),
                "wallet": data.get("wallet", 0),
                "bonus": data.get("bonus", 0)
            }
        else:
            return {"balance": 0, "wallet": 0, "bonus": 0}
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return {"balance": 0, "wallet": 0, "bonus": 0}


# ===============================================================
# 🔹 Routes
# ===============================================================
@app.route('/')
def home():
    return "<h2>School SMS App is Running 🚀</h2>"


# --- Dashboard ---
@app.route('/dashboard')
@login_required
def dashboard():
    categories = Category.query.all()
    balance_info = get_sms_balance()
    return render_template(
        'dashboard.html',
        categories=categories,
        balance=balance_info["balance"],
        wallet=balance_info["wallet"],
        bonus=balance_info["bonus"]
    )


# --- Add Category ---
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


# --- Delete Category ---
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


# --- View Contacts ---
@app.route('/contacts/<int:category_id>')
@login_required
def view_contacts(category_id):
    category = Category.query.get_or_404(category_id)
    return render_template('contacts.html', category=category)


# --- Upload Contacts ---
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
        if 'Phone' not in df.columns:
            flash("Excel file must have a 'Phone' column!", "danger")
            return redirect(url_for('view_contacts', category_id=category_id))

        existing_phones = set(
            contact.phone for contact in Contact.query.filter_by(category_id=category_id).all()
        )
        added_count, skipped_count = 0, 0

        for _, row in df.iterrows():
            phone = str(row['Phone']).strip()
            name = str(row.get('Name', '')).strip() if 'Name' in df.columns else ''
            if not phone or phone == 'nan':
                continue
            if phone in existing_phones:
                skipped_count += 1
                continue
            new_contact = Contact(name=name, phone=phone, category_id=category.id)
            db.session.add(new_contact)
            existing_phones.add(phone)
            added_count += 1

        db.session.commit()
        msg = f"{added_count} contacts added!"
        if skipped_count:
            msg += f" ({skipped_count} duplicates skipped)"
        flash(msg, "success")
    except Exception as e:
        flash(f"Error uploading contacts: {e}", "danger")

    return redirect(url_for('view_contacts', category_id=category_id))


# --- Add, Edit, Delete Contacts (same as before) ---
@app.route('/add_contact/<int:category_id>', methods=['POST'])
@login_required
def add_contact(category_id):
    category = Category.query.get_or_404(category_id)
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    if not phone:
        flash("Phone number is required!", "danger")
        return redirect(url_for('view_contacts', category_id=category_id))
    if Contact.query.filter_by(phone=phone, category_id=category_id).first():
        flash('This phone number already exists!', 'warning')
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
    new_phone = request.form.get('phone', '').strip()
    new_name = request.form.get('name', '').strip()
    if not new_phone:
        flash("Phone number is required!", "danger")
        return redirect(url_for('view_contacts', category_id=contact.category_id))
    if new_phone != contact.phone:
        duplicate = Contact.query.filter_by(phone=new_phone, category_id=contact.category_id).first()
        if duplicate:
            flash('Phone already exists!', 'warning')
            return redirect(url_for('view_contacts', category_id=contact.category_id))
    contact.name, contact.phone = new_name, new_phone
    db.session.commit()
    flash("Contact updated!", "success")
    return redirect(url_for('view_contacts', category_id=contact.category_id))


@app.route('/delete_contact/<int:contact_id>', methods=['POST'])
@login_required
def delete_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    category_id = contact.category_id
    db.session.delete(contact)
    db.session.commit()
    flash("Contact deleted!", "success")
    return redirect(url_for('view_contacts', category_id=category_id))


# --- Send SMS ---
@app.route('/send_sms/<int:category_id>', methods=['POST'])
@login_required
def send_sms(category_id):
    category = Category.query.get_or_404(category_id)
    message = request.form.get('message')
    sender_id = os.getenv("SENDER_ID")
    api_key = os.getenv("MNOTIFY_API_KEY")

    if not message.strip():
        flash("Message cannot be empty!", "danger")
        return redirect(url_for('view_contacts', category_id=category.id))

    contacts = [c.phone for c in category.contacts]
    if not contacts:
        flash("No contacts found!", "danger")
        return redirect(url_for('view_contacts', category_id=category.id))

    url = "https://api.mnotify.com/api/sms/quick"
    payload = {"key": api_key, "recipient": contacts, "sender": sender_id, "message": message}

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            flash("Messages sent successfully!", "success")
        else:
            flash(f"Failed to send SMS: {response.text}", "danger")
    except Exception as e:
        flash(f"Error sending SMS: {e}", "danger")

    return redirect(url_for('view_contacts', category_id=category.id))


# --- Auth Routes ---
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
        flash('Invalid username or password', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('login'))


# --- Clear DB Route ---
@app.route('/clear_db')
def clear_db():
    secret = request.args.get("key")
    if secret != os.getenv("SECRET_KEY"):
        return "❌ Unauthorized access!", 403
    try:
        Contact.query.delete()
        Category.query.delete()
        db.session.commit()
        return "✅ Database cleared successfully!"
    except Exception as e:
        return f"❌ Error clearing DB: {e}"


# --- Run App ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
