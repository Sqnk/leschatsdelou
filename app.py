import os
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from werkzeug.utils import secure_filename

# --- Flask & stockage local (Render OK) ---
app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# SQLite locale (pas de disque Render requis)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///cats.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

db = SQLAlchemy(app)

# --- Modèles ---
class Cat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    birthdate = db.Column(db.Date)
    status = db.Column(db.String(50))
    photo_filename = db.Column(db.String(200))
    vaccinations = db.relationship("Vaccination", backref="cat", lazy=True)
    notes = db.relationship("Note", backref="cat", lazy=True)
    appointments = db.relationship("AppointmentCat", back_populates="cat")

class VaccineType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    vaccinations = db.relationship("Vaccination", backref="vaccine_type", lazy=True)

class Vaccination(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cat_id = db.Column(db.Integer, db.ForeignKey("cat.id"), nullable=False)
    vaccine_type_id = db.Column(db.Integer, db.ForeignKey("vaccine_type.id"), nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow)
    lot = db.Column(db.String(100))
    veterinarian = db.Column(db.String(120))
    reaction = db.Column(db.String(255))

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cat_id = db.Column(db.Integer, db.ForeignKey("cat.id"), nullable=False)
    content = db.Column(db.Text)
    file_name = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200))
    employees = db.relationship("AppointmentEmployee", back_populates="appointment")
    cats = db.relationship("AppointmentCat", back_populates="appointment")

class AppointmentEmployee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointment.id"))
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"))
    appointment = db.relationship("Appointment", back_populates="employees")
    employee = db.relationship("Employee")

class AppointmentCat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointment.id"))
    cat_id = db.Column(db.Integer, db.ForeignKey("cat.id"))
    appointment = db.relationship("Appointment", back_populates="cats")
    cat = db.relationship("Cat", back_populates="appointments")

# --- Helpers ---
def age_text(d: date | None) -> str:
    if not d: return "—"
    today = date.today()
    years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    months = (today.year - d.year) * 12 + (today.month - d.month)
    if today.day < d.day:
        months -= 1
    rem = months - years * 12
    if years <= 0:
        return f"{rem} mois"
    return f"{years} ans, {rem} mois"

# --- Init auto DB ---
with app.app_context():
    inspector = inspect(db.engine)
    if not inspector.get_table_names():
        db.create_all()
        for v in ["Typhus", "Coryza", "Leucose"]:
            db.session.add(VaccineType(name=v))
        for e in ["Alice", "Bob"]:
            db.session.add(Employee(name=e))
        db.session.commit()
        print("✅ Base initialisée.")

# --- Routes fichiers upload ---
@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# --- Pages ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    total_cats = Cat.query.count()
    total_appointments = Appointment.query.count()
    total_employees = Employee.query.count()
    total_vaccines = VaccineType.query.count()
    return render_template("dashboard.html",
                           total_cats=total_cats,
                           total_appointments=total_appointments,
                           total_employees=total_employees,
                           total_vaccines=total_vaccines)

@app.route("/calendrier")
def calendrier():
    return render_template("calendrier.html")

# Recherche “live” façon liste filtrable
@app.route("/recherche")
def recherche():
    return render_template("search_cats.html", q="", cats=Cat.query.order_by(Cat.name).all())

@app.route("/appointments")
def appointments_page():
    now = datetime.utcnow()
    upcoming = Appointment.query.filter(Appointment.date >= now).order_by(Appointment.date).all()
    past = Appointment.query.filter(Appointment.date < now).order_by(Appointment.date.desc()).all()
    return render_template("appointments.html", upcoming=upcoming, past=past)

@app.route("/search/notes")
def search_notes():
    q = request.args.get("q", "").strip()
    results = []
    if q:
        results = Note.query.filter(Note.content.ilike(f"%{q}%")).order_by(Note.created_at.desc()).all()
    return render_template("search_notes.html", q=q, results=results)

@app.route("/search/cats")
def search_cats():
    q = request.args.get("q", "").strip()
    cats = Cat.query.order_by(Cat.name).all() if not q else Cat.query.filter(Cat.name.ilike(f"%{q}%")).order_by(Cat.name).all()
    return render_template("search_cats.html", q=q, cats=cats)

# --- APIs ---
@app.route("/api/cats", methods=["GET", "POST"])
def api_cats():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            return jsonify({"error":"name required"}), 400
        status = request.form.get("status") or None
        birthdate_str = request.form.get("birthdate") or None
        photo = request.files.get("photo")
        birthdate = datetime.strptime(birthdate_str, "%Y-%m-%d").date() if birthdate_str else None

        filename = None
        if photo and photo.filename:
            filename = secure_filename(photo.filename)
            photo.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        c = Cat(name=name, status=status, birthdate=birthdate, photo_filename=filename)
        db.session.add(c)
        db.session.commit()
        return redirect(url_for("index"))

    # GET (avec filtre q pour l’auto-complétion)
    q = request.args.get("q", "").strip()
    query = Cat.query
    if q:
        query = query.filter(Cat.name.ilike(f"%{q}%"))
    cats = query.order_by(Cat.name).all()
    return jsonify([{
        "id": c.id,
        "name": c.name,
        "status": c.status,
        "birthdate": c.birthdate.isoformat() if c.birthdate else None,
        "age_human": age_text(c.birthdate),
        "photo": c.photo_filename
    } for c in cats])

@app.route("/api/appointments", methods=["GET", "POST", "PATCH"])
def api_appointments():
    if request.method == "POST":
        location = request.form.get("location") or "Rendez-vous"
        date_str = request.form.get("date")
        if not date_str:
            return jsonify({"error":"date required"}), 400
        # support datetime-local ("YYYY-MM-DDTHH:MM")
        if "T" in date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
        else:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        a = Appointment(date=dt, location=location)
        db.session.add(a)
        db.session.commit()
        return jsonify({"success": True, "id": a.id})

    if request.method == "PATCH":
        data = request.get_json(force=True)
        appt_id = data.get("id")
        new_start = data.get("start")
        a = Appointment.query.get(appt_id)
        if not a:
            return jsonify({"error":"not found"}), 404
        a.date = datetime.fromisoformat(new_start)
        db.session.commit()
        return jsonify({"success": True})

    # GET pour FullCalendar
    appts = Appointment.query.order_by(Appointment.date).all()
    events = []
    for a in appts:
        events.append({
            "id": a.id,
            "title": a.location or "Rendez-vous",
            "start": a.date.strftime("%Y-%m-%dT%H:%M:%S"),
            "allDay": False,
            "extendedProps": {
                "time": a.date.strftime("%d/%m/%Y %H:%M"),
                "cats": [ac.cat.name for ac in a.cats],
                "employees": [ae.employee.name for ae in a.employees],
                "notes": ""
            }
        })
    # Pour /calendrier (JSON brut si besoin)
    if request.args.get("raw") == "1":
        return jsonify({"count": len(appts), "items": [
            {"id": a.id, "date_iso": a.date.isoformat(), "location": a.location,
             "cats": [ac.cat.name for ac in a.cats],
             "employees": [ae.employee.name for ae in a.employees]} for a in appts
        ]})
    return jsonify(events)

@app.route("/api/employees", methods=["GET","POST"])
def api_employees():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        if not name:
            return jsonify({"error":"name required"}), 400
        db.session.add(Employee(name=name))
        db.session.commit()
        return jsonify({"success": True})
    emps = Employee.query.order_by(Employee.name).all()
    return jsonify([{"id": e.id, "name": e.name} for e in emps])

@app.route("/api/vaccines", methods=["GET","POST"])
def api_vaccines():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        if not name:
            return jsonify({"error":"name required"}), 400
        db.session.add(VaccineType(name=name))
        db.session.commit()
        return jsonify({"success": True})
    vaccines = VaccineType.query.order_by(VaccineType.name).all()
    return jsonify([{"id": v.id, "name": v.name} for v in vaccines])

# --- run ---
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
