# Main file for PythonAnywhere deployment
import os
import sys

# Determine the base directory
basedir = os.path.abspath(os.path.dirname(__file__))

# Set environment variables
os.environ.setdefault('FLASK_ENV', 'production')
os.environ.setdefault('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Use absolute path for database - works both locally and on PythonAnywhere
default_db_path = os.path.join(basedir, 'instance', 'gym_system.db')
os.environ.setdefault('DATABASE_URL', f'sqlite:///{default_db_path}')

# Ensure instance directory exists
instance_dir = os.path.join(basedir, 'instance')
if not os.path.exists(instance_dir):
    os.makedirs(instance_dir, exist_ok=True)

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
        # Format: (name_en, name_ar, description, permissions_dict)
        roles_data = [
            ('owner', 'المالك', 'صلاحية كاملة على جميع البراندات', {
                'is_owner': True, 'can_view_all_brands': True, 'can_manage_members': True,
                'can_manage_subscriptions': True, 'can_view_finance': True, 'can_manage_finance': True,
                'can_view_reports': True, 'can_manage_attendance': True
            }),
            ('brand_manager', 'مدير البراند', 'تحكم كامل في براند واحد', {
                'can_manage_members': True, 'can_manage_subscriptions': True, 'can_view_finance': True,
                'can_manage_finance': True, 'can_view_reports': True, 'can_manage_attendance': True
            }),
            ('receptionist', 'موظف استقبال', 'إدارة العملاء والاشتراكات', {
                'can_manage_members': True, 'can_manage_subscriptions': True, 'can_manage_attendance': True
            }),
            ('finance', 'مالية براند', 'إدارة مالية براند واحد', {
                'can_view_finance': True, 'can_manage_finance': True, 'can_view_reports': True
            }),
            ('finance_admin', 'مالية عامة', 'الاطلاع على مالية جميع البراندات', {
                'can_view_all_brands': True, 'can_view_finance': True, 'can_view_reports': True
            }),
            ('coach', 'مدرب', 'الاطلاع على بيانات شخصية فقط', {
                'can_manage_attendance': True
            }),
        ]

        for name_en, name_ar, description, permissions in roles_data:
            if not Role.query.filter_by(name_en=name_en).first():
                role = Role(name=name_ar, name_en=name_en, description=description, **permissions)
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
        owner_role = Role.query.filter_by(name_en='owner').first()
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
