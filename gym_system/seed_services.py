#!/usr/bin/env python3
"""
Seed default service types for all brands
Run: python seed_services.py
"""
import os
os.environ.setdefault('FLASK_APP', 'run.py')

from app import create_app, db
from app.models.service import ServiceType
from app.models.company import Brand

app = create_app('development')

with app.app_context():
    brands = Brand.query.filter_by(is_active=True).all()
    
    if not brands:
        print("❌ No brands found!")
    else:
        for brand in brands:
            print(f"\n📍 Brand: {brand.name} (ID: {brand.id})")
            
            # Check existing services
            existing = ServiceType.query.filter_by(brand_id=brand.id).all()
            print(f"   Existing services: {len(existing)}")
            
            # Seed defaults
            ServiceType.seed_defaults(brand.id)
            
            # Show new count
            new_count = ServiceType.query.filter_by(brand_id=brand.id).count()
            print(f"   After seeding: {new_count} services")
            
            # List all services
            services = ServiceType.query.filter_by(brand_id=brand.id).all()
            for s in services:
                print(f"      ✓ {s.name} ({s.category})")
    
    print("\n✅ Done!")
