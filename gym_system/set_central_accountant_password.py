from app import create_app, db
from app.models.user import User

app = create_app()

with app.app_context():
    # Set password for central accountant
    user = User.query.filter_by(email='finance2@golden_fitness.com').first()
    if user:
        user.set_password('123456')
        db.session.commit()
        print(f"Password set to '123456' for {user.name} ({user.email})")
    else:
        print("User not found")
