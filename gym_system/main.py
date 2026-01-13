# Main file for PythonAnywhere deployment
import os
import sys

# Set environment variables
os.environ.setdefault('FLASK_ENV', 'production')
os.environ.setdefault('SECRET_KEY', 'your-secret-key-change-this-in-production')
os.environ.setdefault('DATABASE_URL', 'sqlite:////home/gymsystem/sytem-gym/gym_system/instance/gym_system.db')

from app import create_app, db

# Create the application
app = create_app('production')

# For PythonAnywhere WSGI
application = app

def init_database():
    """Initialize database with tables and default data"""
    with app.app_context():
        # Create all tables
        db.create_all()

        # Import models
        from app.models.user import User, Role
        from app.models.company import Company

        # Create roles if not exist
        roles_data = [
            ('owner', 'المالك', 'صلاحية كاملة على جميع البراندات'),
            ('brand_manager', 'مدير البراند', 'تحكم كامل في براند واحد'),
            ('receptionist', 'موظف استقبال', 'إدارة العملاء والاشتراكات'),
            ('finance', 'مالية براند', 'إدارة مالية براند واحد'),
            ('finance_admin', 'مالية عامة', 'الاطلاع على مالية جميع البراندات'),
            ('coach', 'مدرب', 'الاطلاع على بيانات شخصية فقط'),
        ]

        for name, name_ar, description in roles_data:
            if not Role.query.filter_by(name=name).first():
                role = Role(name=name, name_ar=name_ar, description=description)
                db.session.add(role)
                print(f'Created role: {name_ar}')

        db.session.commit()

        # Create default company if not exists
        company = Company.query.first()
        if not company:
            company = Company(name='الشركة الرئيسية')
            db.session.add(company)
            db.session.commit()
            print(f'Created company: {company.name}')

        # Create admin user if not exists
        owner_role = Role.query.filter_by(name='owner').first()
        if owner_role and not User.query.filter_by(role_id=owner_role.id).first():
            admin = User(
                name='مدير النظام',
                email='admin@gym.com',
                role_id=owner_role.id,
                brand_id=None
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('Created admin user: admin@gym.com')

        print('Database initialized successfully!')

if __name__ == '__main__':
    # If run directly, initialize database
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'init':
        init_database()
    else:
        app.run(debug=False)
