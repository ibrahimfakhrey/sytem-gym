#!/usr/bin/env python3
"""
Main entry point for the Gym Management System
"""
import os
from app import create_app, db
from app.models.user import User, Role
from app.models.company import Company, Brand, Branch
from app.models.member import Member
from app.models.subscription import Plan, Subscription
from app.models.attendance import MemberAttendance
from app.models.finance import Income, Expense

# Create the Flask application
app = create_app(os.getenv('FLASK_ENV', 'development'))


@app.shell_context_processor
def make_shell_context():
    """Make database models available in flask shell"""
    return {
        'db': db,
        'User': User,
        'Role': Role,
        'Company': Company,
        'Brand': Brand,
        'Branch': Branch,
        'Member': Member,
        'Plan': Plan,
        'Subscription': Subscription,
        'MemberAttendance': MemberAttendance,
        'Income': Income,
        'Expense': Expense
    }


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
