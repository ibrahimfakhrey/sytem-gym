from app import create_app, db
from app.models.user import User

app = create_app()

with app.app_context():
    # Find brand manager user
    user = User.query.filter_by(email='manager1@champions_gym.com').first()
    if user:
        user.set_password('123456')
        db.session.commit()
        print(f"Password set to '123456' for {user.name} ({user.email})")
    else:
        print("User not found")
