from app import app, db
from models import User

with app.app_context():
    user = User(username="admin")
    user.set_password("12345")
    db.session.add(user)
    db.session.commit()
    print("✅ Admin user created successfully!")
