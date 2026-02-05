#!/usr/bin/env python
"""
Migration: Add is_session_based column to service_types table
Date: 2026-02-05
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_migration():
    from app import create_app, db
    from sqlalchemy import text
    from app.models.service import ServiceType
    
    app = create_app()
    with app.app_context():
        print("Starting migration...")
        
        # 1. Add is_session_based column if not exists
        try:
            db.session.execute(text('ALTER TABLE service_types ADD COLUMN is_session_based BOOLEAN DEFAULT 0'))
            db.session.commit()
            print("✅ Added is_session_based column to service_types")
        except Exception as e:
            if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
                print("⏭️ Column is_session_based already exists, skipping...")
            else:
                print(f"⚠️ Error adding column: {e}")
        
        # 2. Update swimming education services to be session-based
        swimming_education = ServiceType.query.filter(
            ServiceType.name.like('%سباحة تعليم%')
        ).all()
        
        for service in swimming_education:
            service.is_session_based = True
            print(f"✅ Updated '{service.name}' (Brand {service.brand_id}) to session-based")
        
        db.session.commit()
        
        # 3. Add swimming education/recreation to brands that don't have them
        from sqlalchemy import text as sql_text
        brands_with_swimming = db.session.execute(sql_text(
            'SELECT DISTINCT brand_id FROM service_types WHERE name LIKE "%سباحة%"'
        )).fetchall()
        
        for (brand_id,) in brands_with_swimming:
            # Check if has سباحة تعليم
            has_teaching = ServiceType.query.filter_by(brand_id=brand_id, name='سباحة تعليم').first()
            has_recreation = ServiceType.query.filter_by(brand_id=brand_id, name='سباحة ترفيه').first()
            
            if not has_teaching:
                teaching = ServiceType(
                    brand_id=brand_id,
                    name='سباحة تعليم',
                    name_en='swimming_teaching',
                    category='swimming',
                    requires_class_booking=True,
                    is_session_based=True
                )
                db.session.add(teaching)
                print(f"✅ Added 'سباحة تعليم' to brand {brand_id}")
            
            if not has_recreation:
                recreation = ServiceType(
                    brand_id=brand_id,
                    name='سباحة ترفيه',
                    name_en='swimming_recreation',
                    category='swimming',
                    requires_class_booking=False,
                    is_session_based=False
                )
                db.session.add(recreation)
                print(f"✅ Added 'سباحة ترفيه' to brand {brand_id}")
        
        db.session.commit()
        print("\n✅ Migration completed successfully!")

if __name__ == '__main__':
    run_migration()
