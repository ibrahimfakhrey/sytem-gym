from datetime import datetime, date, time
from app import db
from app.models.classes import GymClass, ClassBooking
from app.models.daily_closing import DailyClosing

# Aliases for backwards compatibility
ClassSession = GymClass
Booking = ClassBooking
