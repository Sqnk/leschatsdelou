import os
from datetime import datetime, date
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from werkzeug.utils import secure_filename

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///cats.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
db = SQLAlchemy(app)

# -------------------- Models --------------------
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
    employees = db.relationship("AppointmentEmployee", back_populates="appointment", cascade="all, delete-orphan")
    cats = db.relationship("AppointmentCat", back_populates="appointment", cascade="all, delete-orphan")

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

# -------------------- Utils --------------------
def age_text(d: date | None) -> str:
    if not d:
        return "—"
    today = date.today()
    years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    months = (today.year - d.year) * 12 + (today.month - d.month)
    if today.day < d.day:
        months -= 1
    rem = months - years * 12
    if years <= 0:
        return f"{rem} mois"
    return f"{years} ans, {rem} mois"

# -------------------- Init --------------------
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

# -------------------- Static --------------------
@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -------------------- Pages --------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    total_cats = Cat.query.count()
    total_appointments = Appointment.query.count()
    total_employees = Employee.query.count()
    total_vaccines = VaccineType.query.count()
    return render_template(
        "dashboard.html",
        total_cats=total_cats,
        total_appointments=total_appointments,
        total_employees=total_employees,
        total_vaccines=total_vaccines,
    )

@app.route("/recherche")
def recherche():
    return render_template("search_cats.html", q="", cats=Cat.query.order_by(Cat.name).all())

@app.route("/calendrier")
def calendrier():
    return render_template("calendrier.html")

@app.route("/appointments")
def appointments_page():
    now = datetime.utcnow()
    upcoming = Appointment.query.filter(Appointment.date >= now).order_by(Appointment.date).all()
    past = Appointment.query.filter(Appointment.date < now).order_by(Appointment.date.desc()).all()
    cats = Cat.query.order_by(Cat.name).all()
    employees = Employee.query.order_by(Employee.name).all()
    return render_template("appointments.html", upcoming=upcoming, past=past, cats=cats, employees=employees)

@app.route("/appointments/create", methods=["POST"])
def appointments_create():
    location = request.form.get("location") or "Rendez-vous"
    date_str = request.form.get("date")
    if not date_str:
        return redirect(url_for("appointments_page"))
    dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M") if "T" in date_str else datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    appt = Appointment(date=dt, location=location)
    db.session.add(appt)
    db.session.flush()

    for cid in request.form.getlist("cats[]"):
        if cid.isdigit() and Cat.query.get(int(cid)):
            db.session.add(AppointmentCat(appointment_id=appt.id, cat_id=int(cid)))
    for eid in request.form.getlist("employees[]"):
        if eid.isdigit() and Employee.query.get(int(eid)):
            db.session.add(AppointmentEmployee(appointment_id=appt.id, employee_id=int(eid)))

    db.session.commit()
    return redirect(url_for("appointments_page"))

# -------------------- Fiche chat --------------------
@app.route("/cats/<int:cat_id>")
def cat_detail(cat_id):
    c = Cat.query.get_or_404(cat_id)
    vaccines = VaccineType.query.order_by(VaccineType.name).all()
    vaccs = Vaccination.query.filter_by(cat_id=cat_id).order_by(Vaccination.date.desc()).all()
    notes = Note.query.filter_by(cat_id=cat_id).order_by(Note.created_at.desc()).all()
    return render_template("cat_detail.html", cat=c, vaccines=vaccines, vaccs=vaccs, notes=notes, age_text=age_text)

@app.route("/cats/<int:cat_id>/vaccinations", methods=["POST"])
def add_vaccination(cat_id):
    _ = Cat.query.get_or_404(cat_id)
    vt_id = request.form.get("vaccine_type_id", type=int)
    if not vt_id:
        return redirect(url_for("cat_detail", cat_id=cat_id))
    date_str = request.form.get("date")
    d = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    v = Vaccination(
        cat_id=cat_id,
        vaccine_type_id=vt_id,
        date=d,
        lot=request.form.get("lot") or None,
        veterinarian=request.form.get("veterinarian") or None,
        reaction=request.form.get("reaction") or None,
    )
    db.session.add(v)
    db.session.commit()
    return redirect(url_for("cat_detail", cat_id=cat_id))

@app.route("/cats/<int:cat_id>/notes", methods=["POST"])
def add_note(cat_id):
    _ = Cat.query.get_or_404(cat_id)
    content = (request.form.get("content") or "").strip()
    file = request.files.get("file")
    file_name = None
    if file and file.filename:
        fn = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], fn))
        file_name = fn
    if content or file_name:
        db.session.add(Note(cat_id=cat_id, content=content or None, file_name=file_name))
        db.session.commit()
    return redirect(url_for("cat_detail", cat_id=cat_id))

# -------------------- Recherche notes --------------------
@app.route("/search_notes")
def search_notes():
    notes = Note.query.order_by(Note.created_at.desc()).all()
    return render_template("search_notes.html", notes=notes)

# -------------------- Gestion --------------------
@app.route("/gestion/vaccins", methods=["GET", "POST"])
def gestion_vaccins():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            db.session.add(VaccineType(name=name))
            db.session.commit()
        return redirect(url_for("gestion_vaccins"))
    vaccines = VaccineType.query.order_by(VaccineType.name).all()
    return render_template("manage_vaccines.html", vaccines=vaccines)

@app.route("/gestion/vaccins/supprimer/<int:vaccine_id>", methods=["POST"])
def supprimer_vaccin(vaccine_id):
    v = VaccineType.query.get_or_404(vaccine_id)
    db.session.delete(v)
    db.session.commit()
    return redirect(url_for("gestion_vaccins"))

@app.route("/gestion/employes", methods=["GET", "POST"])
def gestion_employes():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            db.session.add(Employee(name=name))
            db.session.commit()
        return redirect(url_for("gestion_employes"))
    employees = Employee.query.order_by(Employee.name).all()
    return render_template("manage_employees.html", employees=employees)

@app.route("/gestion/employes/supprimer/<int:employee_id>", methods=["POST"])
def supprimer_employe(employee_id):
    e = Employee.query.get_or_404(employee_id)
    db.session.delete(e)
    db.session.commit()
    return redirect(url_for("gestion_employes"))

# -------------------- API cats --------------------
@app.route("/api/cats", methods=["GET", "POST"])
def api_cats():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name required"}), 400
        birthdate = None
        if request.form.get("birthdate"):
            birthdate = datetime.strptime(request.form["birthdate"], "%Y-%m-%d").date()
        photo = request.files.get("photo")
        filename = None
        if photo and photo.filename:
            filename = secure_filename(photo.filename)
            photo.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        db.session.add(Cat(name=name, birthdate=birthdate, status=request.form.get("status") or None, photo_filename=filename))
        db.session.commit()
        return redirect(url_for("index"))

    q = (request.args.get("q") or "").strip()
    query = Cat.query
    if q:
        query = query.filter(Cat.name.ilike(f"%{q}%"))
    cats = query.order_by(Cat.name).all()
    return jsonify(
        [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "birthdate": c.birthdate.isoformat() if c.birthdate else None,
                "age_human": age_text(c.birthdate),
                "photo": c.photo_filename,
            }
            for c in cats
        ]
    )

# -------------------- Healthcheck --------------------
@app.route("/health")
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        return {"status": "ok"}, 200
    except Exception as e:
        return {"status": "db_error", "detail": str(e)}, 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
