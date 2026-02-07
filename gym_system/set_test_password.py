from app import create_app, db
from app.models.user import User

app = create_app()

with app.app_context():
    # Find receptionist user
    user = User.query.filter_by(email='reception1@champions_gym.com').first()
    if user:
        # Use the User model's set_password method
        user.set_password('123456')
        db.session.commit()
        print(f"Password set to '123456' for {user.name} ({user.email})")
    else:
        print("User not found")
