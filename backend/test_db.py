"""Run: python test_db.py  — confirms the database connection and db.py work."""
import db

print("Connecting...")
db.ping()
print("Connected to MongoDB Atlas")

r = db.save_reading({"device": "test", "heart_rate": 75, "spo2": 98, "fall": False})
print("Saved reading:", r)
print("Latest reading:", db.get_latest("test"))

rem = db.create_reminder("medicine", "Take morning medicine", device="test")
print("Created reminder:", rem)
print("Responded:", db.respond_to_reminder(rem["id"], source="button"))

# clean up test data
db.readings.delete_many({"device": "test"})
db.reminders.delete_many({"device": "test"})
print("Cleaned up. Database works!")
