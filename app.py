import os
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, jsonify, session, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from sqlalchemy import text
from werkzeug.utils import secure_filename
from functools import wraps
from flask import session
from zoneinfo import ZoneInfo   # 🔥 ajouter ça
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

TZ_PARIS = ZoneInfo("Europe/Paris")   # 🔥 ajouter ça



def parse_date_optional_time(value):
    if not value:
        return None
    # format date + heure "2025-01-15T10:30"
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        pass
    # format date seule "2025-01-15"
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
        
app = Flask(__name__)

# Chemin du disque persistant Render
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

# Assure l'existence du dossier (utile en local et au 1er boot Render)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "djfKGJDFBGKDBG4873g8347gbdfg873gfdgOIUIOFe")
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", None)
ADMIN_DELETE_PASSWORD = "loulou$2910"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

# --- DATABASE CONFIG --- #
db_url = os.environ.get("DATABASE_URL")

# Security: strip invisible chars
if db_url:
    db_url = db_url.strip()

# Force SQLAlchemy to use psycopg driver
# Replace ANY occurrence of postgres:// with postgresql+psycopg://
if db_url:
    db_url = db_url.replace("postgres://", "postgresql+psycopg://")
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://")

app.config["SQLALCHEMY_DATABASE_URI"] = db_url

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
db = SQLAlchemy(app)
# ============================================================
# MODELS
# ============================================================

class Cat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    birthdate = db.Column(db.Date)
    status = db.Column(db.String(50))
    photo_filename = db.Column(db.String(200))

    identification_number = db.Column(db.String(120))          # 🔥 nouveau
    entry_date = db.Column(db.Date)                            # 🔥 nouveau
    gender = db.Column(db.String(20))                          # 🔥 ajouté aussi (M/F) car absent

    fiv = db.Column(db.Boolean, default=False)
    need_vet = db.Column(db.Boolean, default=False)

    vaccinations = db.relationship("Vaccination", backref="cat", lazy=True)
    notes = db.relationship("Note", backref="cat", lazy=True)
    appointments = db.relationship("AppointmentCat", back_populates="cat")
    tasks = db.relationship("CatTask", back_populates="cat", cascade="all, delete-orphan")
    dewormings = db.relationship("Deworming", backref="cat", lazy=True)

class Weight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cat_id = db.Column(db.Integer, db.ForeignKey("cat.id"), nullable=False)
    date = db.Column(db.Date, default=date.today)
    weight = db.Column(db.Float, nullable=False)  # poids en kg

    cat = db.relationship("Cat", backref="weights")
    
class GeneralAppointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)  # ex : Jardinier, Plombier, Intervention
    start = db.Column(db.DateTime, nullable=False)
    end = db.Column(db.DateTime)
    note = db.Column(db.Text)
    color = db.Column(db.String(20), default="orange")  # couleur dans le calendrier

class VaccineType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

    vaccinations = db.relationship("Vaccination", backref="vaccine_type", lazy=True)


class Vaccination(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cat_id = db.Column(db.Integer, db.ForeignKey("cat.id"), nullable=False)
    vaccine_type_id = db.Column(db.Integer, db.ForeignKey("vaccine_type.id"), nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow)
    primo = db.Column(db.Boolean, default=False)    
    veterinarian = db.Column(db.String(120))
    reaction = db.Column(db.String(255))
    
# --- FERMIFUGE MODEL ---
class Deworming(db.Model):   # traitement vermifuge
    id = db.Column(db.Integer, primary_key=True)
    cat_id = db.Column(db.Integer, db.ForeignKey("cat.id"), nullable=False)

    date = db.Column(db.Date, default=date.today)   # date d’administration
    done_by = db.Column(db.String(120))
    reaction = db.Column(db.String(255))
    note = db.Column(db.Text)                       # optionnel
    

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cat_id = db.Column(db.Integer, db.ForeignKey("cat.id"), nullable=False)
    content = db.Column(db.Text)
    file_name = db.Column(db.String(200))
    author = db.Column(db.String(120))       # auteur de la note
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(TZ_PARIS))
    veterinarian = db.Column(db.String(120))  # vétérinaire associé à la note
    updated_at = db.Column(db.DateTime)


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)

class Veterinarian(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200))
    created_by = db.Column(db.String(120))

    employees = db.relationship(
        "AppointmentEmployee",
        back_populates="appointment",
        cascade="all, delete-orphan",
    )
    cats = db.relationship(
        "AppointmentCat",
        back_populates="appointment",
        cascade="all, delete-orphan",
    )


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

class TaskType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    tasks = db.relationship("CatTask", back_populates="task_type", cascade="all, delete-orphan")


class CatTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cat_id = db.Column(db.Integer, db.ForeignKey("cat.id"), nullable=False)
    task_type_id = db.Column(db.Integer, db.ForeignKey("task_type.id"), nullable=False)

    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(TZ_PARIS), nullable=False)

    due_date = db.Column(db.Date)

    is_done = db.Column(db.Boolean, default=False, nullable=False)

    done_by = db.Column(db.String(120))
    done_at = db.Column(db.DateTime)

    cat = db.relationship("Cat", back_populates="tasks")
    task_type = db.relationship("TaskType", back_populates="tasks")


# ============================================================
# UTILS
# ============================================================

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

def site_protected(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("authenticated") is True:
            return f(*args, **kwargs)
        return redirect(url_for("login"))
    return wrapper
@app.template_filter("age")
def age_filter(d):
    return age_text(d)
        
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pwd = request.form.get("password")
        if pwd == os.environ.get("SITE_PASSWORD"):
            session.permanent = True
            session["authenticated"] = True
            return redirect(url_for("dashboard"))
        else:
            flash("Mot de passe incorrect.", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
    
# ============================================================
# INIT DB (création + données de base)
# ============================================================

with app.app_context():
    inspector = inspect(db.engine)
    if not inspector.get_table_names():
        db.create_all()
        # Vaccins de base
        for v in ["Typhus", "Coryza", "Leucose"]:
            db.session.add(VaccineType(name=v))
        # Employés de base
        for e in ["Alice", "Bob"]:
            db.session.add(Employee(name=e))
        # Vétérinaires de base
        for v in ["Dr Dupont", "Dr Martin"]:
            db.session.add(Veterinarian(name=v))
        db.session.commit()
        print("✅ Base initialisée.")

with app.app_context():
    inspector = inspect(db.engine)

    # Création table si absente
    if "deworming" not in inspector.get_table_names():
        print("➡️ Création table deworming…")
        Deworming.__table__.create(db.engine)
        print("✅ Table deworming créée.")

    # Récupération colonnes ACTUALISÉES
    cols = [c["name"] for c in inspector.get_columns("deworming")]

    if "done_by" not in cols:
        print("➡️ Ajout colonne done_by…")
        db.session.execute(db.text(
            "ALTER TABLE deworming ADD COLUMN done_by VARCHAR(120)"
        ))
        db.session.commit()

    if "reaction" not in cols:
        print("➡️ Ajout colonne reaction…")
        db.session.execute(db.text(
            "ALTER TABLE deworming ADD COLUMN reaction VARCHAR(255)"
        ))
        db.session.commit()

    if "note" not in cols:
        print("➡️ Ajout colonne note…")
        db.session.execute(db.text(
            "ALTER TABLE deworming ADD COLUMN note TEXT"
        ))
        db.session.commit()





# --- Migration: ajouter colonne 'primo' à vaccination ---
with app.app_context():
    inspector = inspect(db.engine)

    cols = [c["name"] for c in inspector.get_columns("vaccination")]


    if "primo" not in cols:
        print("➡️ Ajout de la colonne primo à vaccination...")

        try:
            db.session.execute(db.text(
                "ALTER TABLE vaccination ADD COLUMN primo BOOLEAN DEFAULT FALSE"
            ))
            db.session.commit()
            print("✔️ Colonne primo ajoutée.")
        except Exception as e:
            print("⚠️ Erreur lors de l'ajout de primo :", e)
            db.session.rollback()
        
with app.app_context():
    inspector = inspect(db.engine)
    if "weight" not in inspector.get_table_names():
        print("➡️ Création de la table weight…")
        Weight.__table__.create(db.engine)
        print("✅ Table weight créée.")
        
with app.app_context():
    inspector = inspect(db.engine)
    cols = [col['name'] for col in inspector.get_columns('note')]
    if 'veterinarian' not in cols:
        print("➡️ Ajout de la colonne 'veterinarian' dans la table 'note'…")
        db.session.execute(db.text("ALTER TABLE note ADD COLUMN veterinarian VARCHAR(120)"))
        db.session.commit()
        print("✅ Colonne 'veterinarian' ajoutée.")

    if 'updated_at' not in cols:
        print("➡️ Ajout de la colonne 'updated_at' dans la table 'note'…")
        db.session.execute(db.text("ALTER TABLE note ADD COLUMN updated_at TIMESTAMP"))
        db.session.commit()
        print("✅ Colonne 'updated_at' ajoutée.")

with app.app_context():
    inspector = inspect(db.engine)
    cols = [col["name"] for col in inspector.get_columns("cat")]
    if "need_vet" not in cols:
        print("➡️ Ajout de la colonne 'need_vet' dans la table 'cat'…")
        db.session.execute(db.text("ALTER TABLE cat ADD COLUMN need_vet BOOLEAN DEFAULT FALSE"))
        db.session.commit()
        print("✅ Colonne 'need_vet' ajoutée.")
        
# ➕ Ajout table veterinarian si manquante
with app.app_context():
    inspector = inspect(db.engine)
    if "veterinarian" not in inspector.get_table_names():
        print("➡️ Création de la table veterinarian…")
        Veterinarian.__table__.create(db.engine)
        print("✅ Table veterinarian créée.")

# ➕ Ajout colonne fiv si manquante
with app.app_context():
    inspector = inspect(db.engine)
    cols = [col["name"] for col in inspector.get_columns("cat")]
    if "fiv" not in cols:
        print("➡️ Ajout de la colonne 'fiv' dans la table 'cat'…")
        db.session.execute(db.text("ALTER TABLE cat ADD COLUMN fiv BOOLEAN DEFAULT FALSE"))
        db.session.commit()
        print("✅ Colonne 'fiv' ajoutée.")

with app.app_context():
    inspector = inspect(db.engine)
    cols = [col["name"] for col in inspector.get_columns("cat")]

    if "identification_number" not in cols:
        print("➡️ Ajout colonne identification_number…")
        db.session.execute(db.text("ALTER TABLE cat ADD COLUMN identification_number VARCHAR(120)"))
    
    if "entry_date" not in cols:
        print("➡️ Ajout colonne entry_date…")
        db.session.execute(db.text("ALTER TABLE cat ADD COLUMN entry_date DATE"))

    if "gender" not in cols:
        print("➡️ Ajout colonne gender…")
        db.session.execute(db.text("ALTER TABLE cat ADD COLUMN gender VARCHAR(20)"))

    db.session.commit()
        
with app.app_context():
    inspector = inspect(db.engine)
    cols = [col["name"] for col in inspector.get_columns("appointment")]
    if "created_by" not in cols:
        print("➡️ Ajout de la colonne 'created_by' dans la table 'appointment'…")
        db.session.execute(db.text("ALTER TABLE appointment ADD COLUMN created_by VARCHAR(120)"))
        db.session.commit()
        print("✅ Colonne 'created_by' ajoutée.")

# ➕ Ajout des tables de tâches si manquantes
with app.app_context():
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    if "task_type" not in tables:
        print("➡️ Création de la table task_type…")
        TaskType.__table__.create(db.engine)
        print("✅ Table task_type créée.")

    if "cat_task" not in tables:
        print("➡️ Création de la table cat_task…")
        CatTask.__table__.create(db.engine)
        print("✅ Table cat_task créée.")
        
with app.app_context():
    inspector = inspect(db.engine)
    cols = [col["name"] for col in inspector.get_columns("cat_task")]

    if "done_by" not in cols:
        print("➡️ Ajout de la colonne 'done_by' dans la table 'cat_task'…")
        db.session.execute(db.text("ALTER TABLE cat_task ADD COLUMN done_by VARCHAR(120)"))
    
    if "done_at" not in cols:
        print("➡️ Ajout de la colonne 'done_at' dans la table 'cat_task'…")
        db.session.execute(db.text("ALTER TABLE cat_task ADD COLUMN done_at TIMESTAMP"))

    db.session.commit()
    print("✅ Colonnes 'done_by' et 'done_at' ajoutées.")
    
with app.app_context():
    inspector = inspect(db.engine)
    if "general_appointment" not in inspector.get_table_names():
        print("➡️ Création de la table general_appointment…")
        GeneralAppointment.__table__.create(db.engine)
        print("✅ Table general_appointment créée.")
        
# ============================================================
# STATIC UPLOADS
# ============================================================
@app.route("/cats/<int:cat_id>/delete", methods=["POST"])
@site_protected
def delete_cat(cat_id):
    cat = Cat.query.get_or_404(cat_id)

    # Vérification du mot de passe admin
    password = request.form.get("admin_password", "")
    if password != ADMIN_DELETE_PASSWORD:
        flash("Mot de passe administrateur incorrect.", "danger")
        return redirect(url_for("cat_detail", cat_id=cat_id))

    # Supprimer la photo associée
    if cat.photo_filename:
        photo_path = os.path.join(app.config["UPLOAD_FOLDER"], cat.photo_filename)
        if os.path.exists(photo_path):
            os.remove(photo_path)

    # Supprimer les vaccinations associées
    for v in cat.vaccinations:
        db.session.delete(v)

    # Supprimer les notes associées
    for n in cat.notes:
        db.session.delete(n)

    db.session.delete(cat)
    db.session.commit()

    flash("Chat supprimé.", "success")
    return redirect(url_for("dashboard"))

@app.post("/api/check_admin_password")
def api_check_admin_password():
    data = request.json or {}
    password = data.get("password", "")
    if password == ADMIN_DELETE_PASSWORD:
        return {"ok": True}
    return {"ok": False}, 403
  
# -------------------- Helpers dashboard (vermifuge) --------------------
class DewormDue:
    def __init__(self, cat, last_date, next_due, days_left, status):
        self.cat = cat
        self.last_date = last_date
        self.next_due = next_due
        self.days_left = days_left
        self.status = status

def compute_deworming_due():
    today = date.today()
    limit = today + timedelta(days=7)
    results = []

    cats = Cat.query.filter(Cat.status.notin_(["adopté", "décédé"])).all()

    for cat in cats:
        last = None
        for d in cat.dewormings:
            if not last or d.date > last.date:
                last = d

        if not last:
            continue

        next_due = last.date + timedelta(days=60)
        days_left = (next_due - today).days

        if next_due < today:
            results.append(DewormDue(cat, last.date, next_due, days_left, "late"))
        elif today <= next_due <= limit:
            results.append(DewormDue(cat, last.date, next_due, days_left, "soon"))

    results.sort(key=lambda x: (0 if x.status == "late" else 1, x.days_left))
    return results

  
# ============================================================
# PHOTO — AJOUT / MODIFICATION POUR UN CHAT
# ============================================================

@app.route("/cats/<int:cat_id>/update_photo", methods=["POST"])
@site_protected
def update_cat_photo(cat_id):
    cat = Cat.query.get_or_404(cat_id)

    if "photo" not in request.files:
        flash("Aucune photo reçue.", "danger")
        return redirect(url_for("cat_detail", cat_id=cat.id))

    photo = request.files["photo"]

    if photo.filename == "":
        flash("Aucun fichier sélectionné.", "danger")
        return redirect(url_for("cat_detail", cat_id=cat.id))

    filename = secure_filename(photo.filename)
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    # Sauvegarde sur le disque permanent Render
    photo.save(save_path)

    # Met à jour le chat en base
    cat.photo_filename = filename
    db.session.commit()

    flash("Photo mise à jour !", "success")
    return redirect(url_for("cat_detail", cat_id=cat.id))

@app.route("/notes/<int:note_id>/edit", methods=["POST"])
@site_protected
def edit_note(note_id):
    note = Note.query.get_or_404(note_id)

    # Contenu
    content = (request.form.get("content") or "").strip()
    if content:
        note.content = content
    else:
        note.content = None

    # Auteur
    author = request.form.get("author")
    if author == "":
        author = None
    note.author = author

    # Vétérinaire
    veterinarian = request.form.get("veterinarian")
    if veterinarian == "":
        veterinarian = None
    note.veterinarian = veterinarian

    # Date de modification
    note.updated_at = datetime.now(TZ_PARIS)

    db.session.commit()

    return redirect(url_for("cat_detail", cat_id=note.cat_id))


@app.route("/notes/<int:note_id>/delete", methods=["POST"])
@site_protected
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)

    # Supprimer fichier joint
    if note.file_name:
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], note.file_name)
        if os.path.exists(file_path):
            os.remove(file_path)

    cat_id = note.cat_id
    db.session.delete(note)
    db.session.commit()

    return redirect(url_for("cat_detail", cat_id=cat_id))

@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)
    


# ============================================================
# PAGES DE BASE
# ============================================================

@app.route("/appointments/<int:appointment_id>/edit")
@site_protected
def appointment_edit(appointment_id):
    appt = Appointment.query.get_or_404(appointment_id)
    cats = Cat.query.order_by(Cat.name).all()
    employees = Employee.query.order_by(Employee.name).all()
    veterinarians = Veterinarian.query.order_by(Veterinarian.name).all()  # 🔥 MANQUAIT !

    return render_template(
        "appointment_edit.html",
        appt=appt,
        cats=cats,
        employees=employees,
        veterinarians=veterinarians  # 🔥 MANQUAIT AUSSI !
    )
    
@app.route("/appointments/<int:appointment_id>/delete", methods=["POST"])
@site_protected
def appointment_delete(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)

    # Suppression des relations chats et employés
    AppointmentCat.query.filter_by(appointment_id=appointment_id).delete()
    AppointmentEmployee.query.filter_by(appointment_id=appointment_id).delete()

    db.session.delete(appointment)
    db.session.commit()

    return redirect(url_for("appointments_page"))

@app.route("/appointments/<int:appointment_id>/delete", methods=["POST"])
@site_protected
def delete_appointment(appointment_id):
    appt = Appointment.query.get_or_404(appointment_id)

    db.session.delete(appt)
    db.session.commit()

    return redirect(url_for("appointments"))

@app.route("/appointments/<int:appointment_id>/edit", methods=["POST"])
@site_protected
def appointment_update(appointment_id):
    appt = Appointment.query.get_or_404(appointment_id)

    # Update date + lieu
    date_str = request.form.get("date")
    if date_str:
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
        # ❌ pas de dt.replace(tzinfo=TZ_PARIS) ici
        appt.date = dt

    appt.location = request.form.get("location") or "Rendez-vous"
    
    # Reset les chats
    AppointmentCat.query.filter_by(appointment_id=appointment_id).delete()
    for cid in request.form.getlist("cats[]"):
        if cid.isdigit():
            db.session.add(AppointmentCat(appointment_id=appointment_id, cat_id=int(cid)))

    # Reset les employés
    AppointmentEmployee.query.filter_by(appointment_id=appointment_id).delete()
    for eid in request.form.getlist("employees[]"):
        if eid.isdigit():
            db.session.add(AppointmentEmployee(appointment_id=appointment_id, employee_id=int(eid)))

    db.session.commit()
    return redirect(url_for("appointments_page"))

# ============================================================
# GENERAL APPOINTMENTS — EDIT / UPDATE / DELETE
# ============================================================

@app.route("/general_appointment/<int:appointment_id>/edit")
@site_protected
def general_appointment_edit(appointment_id):
    appt = GeneralAppointment.query.get_or_404(appointment_id)
    return render_template("general_appointment_edit.html", appt=appt)

@app.route("/general_appointment/<int:appointment_id>/update", methods=["POST"])
@site_protected
def general_appointment_update(appointment_id):
    appt = GeneralAppointment.query.get_or_404(appointment_id)

    appt.title = request.form.get("title") or appt.title
    appt.note = request.form.get("note") or None

    start_str = request.form.get("start")
    end_str = request.form.get("end")

    start = parse_date_optional_time(start_str)
    end = parse_date_optional_time(end_str)

    # ❌ plus de .replace(tzinfo=TZ_PARIS) avant stockage
    appt.start = start
    appt.end = end

    db.session.commit()
    return redirect(url_for("appointments_page"))


@app.route("/general_appointment/<int:appointment_id>/delete", methods=["POST"])
@site_protected
def general_appointment_delete(appointment_id):
    appt = GeneralAppointment.query.get_or_404(appointment_id)
    db.session.delete(appt)
    db.session.commit()
    return redirect(url_for("appointments_page"))

# (reste du fichier)
@app.route("/")
@site_protected
def index():
    return redirect(url_for("cats"))
    
# -------------------- Helpers dashboard --------------------
def compute_vaccines_due(days: int = 30):
    today = date.today()
    limit = today + timedelta(days=days)
    results = []

    vaccine_types = VaccineType.query.all()
    cats = Cat.query.filter(Cat.status.notin_(["adopté", "décédé"])).all()

    for cat in cats:

        # Récupère la dernière injection par type
        last_by_type = {}
        for v in cat.vaccinations:
            vt = v.vaccine_type_id
            if vt not in last_by_type or v.date > last_by_type[vt].date:
                last_by_type[vt] = v

        # Pour chaque type de vaccin, on calcule le prochain rappel
        for vt in vaccine_types:
            vt_id = vt.id

            if vt_id not in last_by_type:
                continue

            last_vacc = last_by_type[vt_id]

            # Primo = rappel 30 jours sinon 1 an
            if last_vacc.primo:
                next_due = last_vacc.date + timedelta(days=30)
            else:
                next_due = last_vacc.date + timedelta(days=365)

            days_left = (next_due - today).days

            # En retard
            if next_due < today:
                results.append({
                    "cat": cat,
                    "vaccine": vt,
                    "last_date": last_vacc.date,
                    "next_due": next_due,
                    "days_left": days_left,
                    "status": "late"
                })
                continue

            # À venir dans X jours
            if today <= next_due <= limit:
                results.append({
                    "cat": cat,
                    "vaccine": vt,
                    "last_date": last_vacc.date,
                    "next_due": next_due,
                    "days_left": days_left,
                    "status": "soon"
                })

    # tri par urgence
    results.sort(key=lambda x: (
        0 if x["status"] == "late" else 1,
        x["days_left"]
    ))

    return results




@app.route("/dashboard")
@site_protected
def dashboard():

    # ------------------ Vaccins ------------------
    vaccines_due = compute_vaccines_due(30)
    vaccines_late_count = sum(1 for v in vaccines_due if v["status"] == "late")
    vaccines_due_count  = sum(1 for v in vaccines_due if v["status"] == "soon")

        # ------------------ Vermifuges ------------------
    deworm_due = compute_deworming_due()
    deworm_late_count = sum(1 for d in deworm_due if d.status == "late")
    deworm_due_count  = sum(1 for d in deworm_due if d.status == "soon")


    # ------------------ Stats ------------------
    stats = {
        "cats": Cat.query.filter(Cat.status.notin_(["adopté", "décédé", "famille d'accueil"])).count(),
        "appointments": Appointment.query.count(),
        "employees": Employee.query.count(),
    }

    tasks_pending_count = CatTask.query.filter_by(is_done=False).count()
    employees = Employee.query.order_by(Employee.name.asc()).all()

    return render_template(
        "dashboard.html",

        # --- stats génériques ---
        stats=stats,
        total_cats=stats["cats"],
        total_appointments=stats["appointments"],
        total_employees=stats["employees"],
        tasks_pending_count=tasks_pending_count,

        # --- vaccins ---
        vaccines_due=vaccines_due,
        vaccines_late_count=vaccines_late_count,
        vaccines_due_count=vaccines_due_count,

        # --- vermifuges ---
        deworm_due=deworm_due,
        deworm_late_count=deworm_late_count,
        deworm_due_count=deworm_due_count,

        # --- contenu pour le dashboard ---
        cats=Cat.query.filter(Cat.status.notin_(["adopté", "décédé"])).order_by(Cat.name).all(),
        employees=employees,
        veterinarians=Veterinarian.query.all(),
    )





@app.route("/recherche")
@site_protected
def recherche():
    return render_template("search_cats.html", q="", cats=Cat.query.order_by(Cat.name).all())


@app.route("/calendrier")
@site_protected
def calendrier():
    return render_template("calendrier.html")


@app.route("/cats")
@site_protected
def cats():
    # Liste complète des chats (pour l’onglet liste)
    cats = Cat.query.order_by(Cat.name).all()

    # Liste pour auteurs de notes et éventuellement assignation
    employees = Employee.query.order_by(Employee.name).all()

    return render_template(
        "cats.html",
        cats=cats,
        employees=employees
    )

# ===========================================
# GENERATE DOCUMENTS (Bon de commande + Rapport)
# ===========================================

@app.route("/documents")
@site_protected
def documents():
    # Liste des produits (PDF importé)
    products = [
        ("1000006", "Bidon 5L détergent bactéricide flash DP pin"),
        ("1000005", "Bidon 5L détergent bactéricide flash DP citron"),
        ("1000108", "Pulvérisateur 750ml dégraissant virucide IDOS"),
        ("002023104", "Bidon 1L détergent vaisselle"),
        ("002020105", "Bidon 5L lessive liquide enzymes"),
        ("123919", "Bidon 5L eau de javel 9.6°"),
        ("002026002", "Pousse mousse savon mains 500ml"),
        ("002061495", "Pulvérisateur 750ml nettoyant vitres"),
        ("022207001", "Bidon 5L vinaigre ecocert"),
        ("1000126", "Flacon 750ml WC gel gely bact"),
        ("124097", "Carton 500 SAD 50L blancs"),
        ("124858", "Carton 100 SAD 160L 55mm"),
        ("124056", "Carton 500 SAD 30L corbeilles"),
        ("132266", "Gant MAPA S-M-L-XL"),
        ("1052", "Boîte 100 gants jetables latex S-M-L-XL"),
        ("1082", "Boîte 100 gants jetables nitrile bleu S-M-L-XL"),
        ("T376", "Paquet 10 éponges double face vert"),
        ("00HE44", "Paquet 10 éponges n°4"),
        ("2501003101", "Paquet 10 éponges magiques"),
        ("T184", "Sachet 5 lavettes microfibre"),
        ("T117", "Paquet 10 éponges inox"),
        ("0702070", "Seau essoreur pour frange espagnol"),
        ("1261", "Frange espagnol microfibre bleue"),
        ("406900", "Colis 72 rouleaux papier toilette"),
        ("416895", "Colis 6 bobines dévidage central"),
        ("0212700001", "Aspirateur poussière"),
        ("022000730", "Lot 20 sacs aspirateur"),
    ]

    return render_template("documents.html", products=products)

    
@app.route("/documents/generate_pdf", methods=["POST"])
def generate_pdf():
    import io
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    # Récupère la liste des produits
    products = [
        ("1000006", "Bidon 5L détergent bactéricide flash DP pin"),
        ("1000005", "Bidon 5L détergent bactéricide flash DP citron"),
        ("1000108", "Pulvérisateur 750ml dégraissant virucide IDOS"),
        ("002023104", "Bidon 1L détergent vaisselle"),
        ("002020105", "Bidon 5L lessive liquide enzymes"),
        ("123919", "Bidon 5L eau de javel 9.6°"),
        ("002026002", "Pousse mousse savon mains 500ml"),
        ("002061495", "Pulvérisateur 750ml nettoyant vitres"),
        ("022207001", "Bidon 5L vinaigre ecocert"),
        ("1000126", "Flacon 750ml WC gel gely bact"),
        ("124097", "Carton 500 SAD 50L blancs"),
        ("124858", "Carton 100 SAD 160L 55mm"),
        ("124056", "Carton 500 SAD 30L corbeilles"),
        ("132266", "Gant MAPA S-M-L-XL"),
        ("1052", "Boîte 100 gants jetables latex S-M-L-XL"),
        ("1082", "Boîte 100 gants jetables nitrile bleu S-M-L-XL"),
        ("T376", "Paquet 10 éponges double face vert"),
        ("00HE44", "Paquet 10 éponges n°4"),
        ("2501003101", "Paquet 10 éponges magiques"),
        ("T184", "Sachet 5 lavettes microfibre"),
        ("T117", "Paquet 10 éponges inox"),
        ("0702070", "Seau essoreur pour frange espagnol"),
        ("1261", "Frange espagnol microfibre bleue"),
        ("406900", "Colis 72 rouleaux papier toilette"),
        ("416895", "Colis 6 bobines dévidage central"),
        ("0212700001", "Aspirateur poussière"),
        ("022000730", "Lot 20 sacs aspirateur"),
    ]

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    green = colors.Color(0/255, 128/255, 0/255)

    # TITRE
    c.setFillColor(green)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(width/2, height - 60, "IDF Diffusion")

    # SOUS TITRE
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(width/2, height - 95, "BON DE PRÉ-COMMANDE")

    # DATE
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.black)
    c.drawString(40, height - 140, f"Date : {datetime.now().strftime('%d/%m/%Y')}")

    # ADRESSE
    c.setFont("Helvetica-Oblique", 12)
    c.drawCentredString(width/2, height - 165,
        "Refuge de Louveciennes – 24 route de Versailles – 78430 LOUVECIENNES"
    )

    # TABLEAU (taille réduite + traits verticaux)
    start_x = 30
    start_y = height - 220

    # largeurs réduites
    col_ref = 80
    col_label = 300
    col_qte = 50
    line_h = 20

    table_width = col_ref + col_label + col_qte

    # En-tête
    c.setFont("Helvetica-Bold", 11)
    c.rect(start_x, start_y, table_width, line_h)

    # traits verticaux (en-tête)
    c.line(start_x + col_ref, start_y, start_x + col_ref, start_y + line_h)
    c.line(start_x + col_ref + col_label, start_y, start_x + col_ref + col_label, start_y + line_h)

    c.drawString(start_x + 5, start_y + 6, "Référence")
    c.drawString(start_x + col_ref + 5, start_y + 6, "Désignation")
    c.drawString(start_x + col_ref + col_label + 5, start_y + 6, "Qté")

    # lignes produits
    y = start_y - line_h
    c.setFont("Helvetica", 10)

    for ref, label in products:
    qty = request.form.get(ref, "").strip()

    # rectangle ligne
    c.rect(start_x, y, table_width, line_h)

    # traits verticaux
    c.line(start_x + col_ref, y, start_x + col_ref, y + line_h)
    c.line(start_x + col_ref + col_label, y, start_x + col_ref + col_label, y + line_h)

    # texte
    c.drawString(start_x + 5, y + 5, ref)
    c.drawString(start_x + col_ref + 5, y + 5, label)
    c.drawString(start_x + col_ref + col_label + 5, y + 5, qty)

    y -= line_h


    for ref, label in products:
        qty = request.form.get(ref, "").strip()

        c.rect(start_x, y, col_ref + col_label + col_qte, line_h)
        c.drawString(start_x + 5, y + 5, ref)
        c.drawString(start_x + col_ref + 5, y + 5, label)
        c.drawString(start_x + col_ref + col_label + 5, y + 5, qty)

        y -= line_h

    c.showPage()
    c.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True,
                     download_name="bon_de_commande.pdf",
                     mimetype="application/pdf")



    
# ============================================================
# APPOINTMENTS (PAGE + CREATION)
# ============================================================

@app.route("/appointments")
@site_protected
def appointments_page():
    # "now" en heure de Paris mais SANS timezone (comme stocké en base)
    now_paris = datetime.now(TZ_PARIS)
    now = now_paris.replace(tzinfo=None)

    upcoming = Appointment.query.filter(
        Appointment.date >= now
    ).order_by(Appointment.date).all()

    past = Appointment.query.filter(
        Appointment.date < now
    ).order_by(Appointment.date.desc()).all()
    
    # 🔧 Force timezone Paris pour tous les RDV pour l'AFFICHAGE
    for a in upcoming:
        if a.date.tzinfo is None:
            a.date = a.date.replace(tzinfo=TZ_PARIS)

    for a in past:
        if a.date.tzinfo is None:
            a.date = a.date.replace(tzinfo=TZ_PARIS)



    cats = Cat.query.order_by(Cat.name).all()
    employees = Employee.query.order_by(Employee.name).all()
    veterinarians = Veterinarian.query.order_by(Veterinarian.name).all()

    general = GeneralAppointment.query.order_by(GeneralAppointment.start.desc()).all()
    
    # 🔧 Force timezone Paris pour les RDV généraux
    for g in general:
        if g.start and g.start.tzinfo is None:
            g.start = g.start.replace(tzinfo=TZ_PARIS)
        if g.end and g.end.tzinfo is None:
            g.end = g.end.replace(tzinfo=TZ_PARIS)


    return render_template(
    "appointments.html",
    upcoming=upcoming,
    past=past,
    general=general,
    cats=cats,
    employees=employees,
    veterinarians=veterinarians,
    datetime=datetime,
    TZ_PARIS=TZ_PARIS,
)



@app.route("/appointments/create", methods=["POST"])
@site_protected
def appointments_create():
    location = request.form.get("location") or "Rendez-vous"
    date_str = request.form.get("date")
    if not date_str:
        return redirect(url_for("appointments_page"))

    # <input type="datetime-local"> => "YYYY-MM-DDTHH:MM"
    if "T" in date_str:
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
    else:
        # fallback si autre format
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")

    appt = Appointment(
        date=dt,  # 🔥 on stocke NAÏF, sans tzinfo
        location=location,
        created_by=request.form.get("created_by") or None
    )

    db.session.add(appt)
    db.session.flush()  # pour récupérer appt.id


    # Chats sélectionnés
    raw_cats = request.form.get("cats[]", "")  # ex: "1,3,7"
    for cid in raw_cats.split(","):
        cid = cid.strip()
        if cid.isdigit() and Cat.query.get(int(cid)):
            db.session.add(AppointmentCat(appointment_id=appt.id, cat_id=int(cid)))

    # Employés sélectionnés
    for eid in request.form.getlist("employees[]"):
        if eid.isdigit() and Employee.query.get(int(eid)):
            db.session.add(AppointmentEmployee(appointment_id=appt.id, employee_id=int(eid)))

    db.session.commit()
    return redirect(url_for("appointments_page"))

@app.route("/appointments/create_general", methods=["POST"])
@site_protected
def appointments_create_general():
    title = request.form.get("title") or "Intervention"
    start_str = request.form.get("start")
    end_str = request.form.get("end")
    note = request.form.get("note")

    if not start_str:
        return redirect(url_for("appointments_page"))

    # On parse en NAÏF (heure locale), sans timezone
    start = parse_date_optional_time(start_str)
    end = parse_date_optional_time(end_str) if end_str else None

    ga = GeneralAppointment(
        title=title,
        start=start,   # 🔥 NAÏF
        end=end,       # 🔥 NAÏF
        note=note,
        color="orange"
    )

    db.session.add(ga)
    db.session.commit()

    return redirect(url_for("appointments_page"))

# -------------------- FullCalendar events --------------------

@app.route("/appointments_events")
@site_protected
def appointments_events():
    """Ancien endpoint JSON simple pour le calendrier (compatibilité)."""
    events = []
    for a in Appointment.query.all():
        label = a.location or "Rendez-vous"
        cats = ", ".join(ca.cat.name for ca in a.cats)
        employees = ", ".join(emp.employee.name for emp in a.employees)

        title = label
        if cats:
            title += f" — Chats : {cats}"
        if employees:
            title += f" — Employés : {employees}"

        events.append({
            "title": title,
            "start": a.date.isoformat(),
        })

    return jsonify(events)


@app.route("/api/appointments")
@site_protected
def api_appointments():
    """Endpoint JSON détaillé pour le calendrier (FullCalendar du dashboard)."""
    events = []

    # --- RDV chats / vétérinaires --- (bleu)
    for a in Appointment.query.all():
        cats_str = ", ".join(ca.cat.name for ca in a.cats)
        emps_str = ", ".join(emp.employee.name for emp in a.employees)

        tooltip_lines = [
            a.date.astimezone(TZ_PARIS).strftime("%d/%m/%Y %H:%M"),
            f"Lieu : {a.location or '—'}",
        ]
        if cats_str:
            tooltip_lines.append(f"Chats : {cats_str}")
        if emps_str:
            tooltip_lines.append(f"Employés : {emps_str}")

        tooltip = "\n".join(tooltip_lines)

        events.append({
            "id": a.id,
            "title": a.location or "Rendez-vous",
            "start": a.date.isoformat(),
            "backgroundColor": "#3A7AFE",     # 💙 RDV chats = bleu
            "borderColor": "#3A7AFE",
            "extendedProps": {
                "tooltip": tooltip,
                "cats": cats_str,
                "employees": emps_str,
                "location": a.location or "",
            },
            "url": url_for("appointments_page"),
        })

    # --- RDV généraux --- (orange)
    for g in GeneralAppointment.query.all():

        tooltip = g.start.astimezone(TZ_PARIS).strftime("%d/%m/%Y %H:%M")
        if g.end:
            tooltip += " → " + g.end.astimezone(TZ_PARIS).strftime("%d/%m/%Y %H:%M")
        if g.note:
            tooltip += f"\nNote : {g.note}"

        events.append({
            "id": f"g-{g.id}",
            "title": g.title,
            "start": g.start.isoformat(),
            "end": g.end.isoformat() if g.end else None,

            "backgroundColor": "#FFA500",     # 🟧 RDV généraux = orange
            "borderColor": "#FFA500",

            "extendedProps": {
                "tooltip": tooltip,
                "location": g.title,
                "cats": "",
                "employees": "",
            }
        })

    return jsonify(events)



# ============================================================
# FICHE CHAT
# ============================================================

@app.route("/cats/<int:cat_id>")
@site_protected
def cat_detail(cat_id):
    c = Cat.query.get_or_404(cat_id)
    vaccines = VaccineType.query.order_by(VaccineType.name).all()
    vaccs = Vaccination.query.filter_by(cat_id=cat_id).order_by(Vaccination.date.desc()).all()
    notes = Note.query.filter_by(cat_id=cat_id).order_by(Note.created_at.desc()).all()
    employees = Employee.query.order_by(Employee.name).all()
    veterinarians = Veterinarian.query.order_by(Veterinarian.name).all()
    task_types = TaskType.query.filter_by(is_active=True).order_by(TaskType.name).all()
    dewormings = Deworming.query.filter_by(cat_id=cat_id).order_by(Deworming.date.desc()).all()


    return render_template(
        "cat_detail.html",
        cat=c,
        vaccines=vaccines,
        vaccs=vaccs,
        notes=notes,
        employees=employees,
        veterinarians=veterinarians,
        age_text=age_text,
        task_types=task_types,
        tasks=c.tasks,
        weights=c.weights,
        TZ_PARIS=TZ_PARIS,
        dewormings=dewormings,
            
    )

@app.route("/cats/<int:cat_id>/weight/add", methods=["POST"])
@site_protected
def add_weight(cat_id):
    _ = Cat.query.get_or_404(cat_id)

    date_str = request.form.get("date")
    weight_str = request.form.get("weight")

    if not weight_str:
        flash("Poids invalide.", "danger")
        return redirect(url_for("cat_detail", cat_id=cat_id) + "?tab=weights")

    try:
        w = float(weight_str.replace(",", "."))
    except:
        flash("Format de poids incorrect.", "danger")
        return redirect(url_for("cat_detail", cat_id=cat_id) + "?tab=weights")

    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        d = date.today()

    new_weight = Weight(cat_id=cat_id, date=d, weight=w)
    db.session.add(new_weight)
    db.session.commit()

    flash("Pesée ajoutée.", "success")
    return redirect(url_for("cat_detail", cat_id=cat_id) + "?tab=weights")

@app.route("/cats/<int:cat_id>/deworming/add", methods=["POST"])
@site_protected
def add_deworming(cat_id):
    _ = Cat.query.get_or_404(cat_id)

    date_str = request.form.get("date")
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        d = date.today()

    done_by = request.form.get("done_by") or None
    reaction = request.form.get("reaction") or None
    note = request.form.get("note") or None

    new_d = Deworming(
        cat_id=cat_id,
        date=d,
        done_by=done_by,
        reaction=reaction,
        note=note
    )

    db.session.add(new_d)
    db.session.commit()

    return redirect(url_for("cat_detail", cat_id=cat_id) + "?tab=deworming")

@app.route("/cats/<int:cat_id>/deworming/<int:dw_id>/delete", methods=["POST"])
@site_protected
def delete_deworming(cat_id, dw_id):
    d = Deworming.query.get_or_404(dw_id)
    db.session.delete(d)
    db.session.commit()
    return redirect(url_for("cat_detail", cat_id=cat_id) + "?tab=deworming")
    
@app.route("/cats/<int:cat_id>/deworming/<int:dw_id>/edit", methods=["POST"])
@site_protected
def edit_deworming(cat_id, dw_id):
    d = Deworming.query.get_or_404(dw_id)

    date_str = request.form.get("date")
    if date_str:
        d.date = datetime.strptime(date_str, "%Y-%m-%d").date()

    d.done_by = request.form.get("done_by") or None
    d.reaction = request.form.get("reaction") or None
    d.note = request.form.get("note") or None

    db.session.commit()
    return redirect(url_for("cat_detail", cat_id=cat_id) + "?tab=deworming")

@app.route("/cats/<int:cat_id>/update_full", methods=["POST"])
@site_protected
def update_cat_full(cat_id):
    cat = Cat.query.get_or_404(cat_id)

    # -------------------------------
    # Statut
    # -------------------------------
    cat.status = request.form.get("status") or None

    # -------------------------------
    # Numéro d'identification
    # -------------------------------
    cat.identification_number = request.form.get("identification_number") or None

    # -------------------------------
    # Date d'entrée
    # -------------------------------
    entry = request.form.get("entry_date")
    if entry:
        try:
            cat.entry_date = datetime.strptime(entry, "%Y-%m-%d").date()
        except:
            pass

    # -------------------------------
    # FIV & Besoin veto
    # -------------------------------
    cat.fiv = "fiv" in request.form
    cat.need_vet = "need_vet" in request.form

    # -------------------------------
    # PHOTO (optionnelle)
    # -------------------------------
    photo = request.files.get("photo")

    if photo and photo.filename.strip():

        filename = secure_filename(photo.filename)
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        # Sauvegarde de la nouvelle photo
        try:
            photo.save(save_path)
        except Exception as e:
            flash("Erreur lors de l’enregistrement de la photo.", "danger")
            return redirect(url_for("cat_detail", cat_id=cat.id))

        # Suppression ancienne photo
        if cat.photo_filename:
            old_path = os.path.join(app.config["UPLOAD_FOLDER"], cat.photo_filename)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except:
                    pass

        cat.photo_filename = filename

    # -------------------------------
    # MAJ DB
    # -------------------------------
    db.session.commit()
    flash("Informations du chat mises à jour.", "success")

    return redirect(url_for("cat_detail", cat_id=cat.id))


@app.route("/cats/<int:cat_id>/vaccinations", methods=["POST"])
@site_protected
def add_vaccination(cat_id):
    _ = Cat.query.get_or_404(cat_id)
    vt_id = request.form.get("vaccine_type_id", type=int)
    if not vt_id:
        return redirect(url_for("cat_detail", cat_id=cat_id))

    date_str = request.form.get("date")
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        d = date.today()
    
    primo = ("primo" in request.form)

    v = Vaccination(
        cat_id=cat_id,
        vaccine_type_id=vt_id,
        date=d,
        primo=primo,        
        veterinarian=request.form.get("veterinarian") or None,
        reaction=request.form.get("reaction") or None,
    )
    db.session.add(v)
    db.session.commit()
    return redirect(url_for("cat_detail", cat_id=cat_id))

@app.route("/cats/<int:cat_id>/vaccinations/<int:vacc_id>/delete", methods=["POST"])
@site_protected
def delete_vaccination(cat_id, vacc_id):
    v = Vaccination.query.get_or_404(vacc_id)
    db.session.delete(v)
    db.session.commit()
    return redirect(url_for("cat_detail", cat_id=cat_id) + "?tab=vaccins")


@app.route("/cats/<int:cat_id>/vaccinations/<int:vacc_id>/edit", methods=["POST"])
@site_protected
def edit_vaccination(cat_id, vacc_id):
    v = Vaccination.query.get_or_404(vacc_id)

    vt_id = request.form.get("vaccine_type_id", type=int)
    date_str = request.form.get("date")

    if vt_id:
        v.vaccine_type_id = vt_id

    if date_str:
        v.date = datetime.strptime(date_str, "%Y-%m-%d").date()

    v.primo = ("primo" in request.form)
    v.veterinarian = request.form.get("veterinarian") or None
    v.reaction = request.form.get("reaction") or None

    db.session.commit()

    return redirect(url_for("cat_detail", cat_id=cat_id) + "?tab=vaccins")

@app.route("/cats/<int:cat_id>/notes", methods=["POST"])
@site_protected
def add_note(cat_id):
    # Vérifie que le chat existe
    _ = Cat.query.get_or_404(cat_id)

    # Récupération du contenu
    content = (request.form.get("content") or "").strip()

    # Auteur depuis la liste déroulante
     
    author = request.form.get("author")
    if author == "":
        author = None

    # Vétérinaire depuis la liste déroulante
    veterinarian = request.form.get("veterinarian")
    if veterinarian == "":
        veterinarian = None

    # Gestion fichier
    file = request.files.get("file")
    file_name = None

    if file and file.filename.strip():
        file_name = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], file_name))
        return redirect(url_for("cat_detail", cat_id=cat_id))

    # Création de la note
    new_note = Note(
        cat_id=cat_id,
        content=content or None,
        file_name=file_name,
        author=author,
        veterinarian=veterinarian,
        created_at=datetime.now(TZ_PARIS)
    )

    db.session.add(new_note)
    db.session.commit()

    return redirect(url_for("cat_detail", cat_id=cat_id))



# ============================================================
# RECHERCHE DE NOTES
# ============================================================

@app.route("/search_notes")
@site_protected
def search_notes():
    notes = Note.query.order_by(Note.created_at.desc()).all()
    employees = Employee.query.order_by(Employee.name).all()
    veterinarians = Veterinarian.query.order_by(Veterinarian.name).all()  # ✔ à ajouter

    return render_template(
        "search_notes.html",
        notes=notes,
        employees=employees,
        veterinarians=veterinarians  # ✔ à envoyer au template
    )


@app.route("/api/search_notes")
@site_protected
def api_search_notes():
    q = (request.args.get("q") or "").strip().lower()
    cat_id = (request.args.get("cat") or "").strip()
    author = (request.args.get("author") or "").strip()
    vet = request.args.get("vet")
    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()

    notes = Note.query.join(Cat)

    # --- Recherche texte ---
    if q:
        notes = notes.filter(
            db.or_(
                Note.content.ilike(f"%{q}%"),
                Note.author.ilike(f"%{q}%"),
                Cat.name.ilike(f"%{q}%"),
            )
        )

    # --- Filtre chat ---
    if cat_id:
        notes = notes.filter(Note.cat_id == cat_id)

    # --- Filtre auteur ---
    if author:
        notes = notes.filter(Note.author == author)
    
    if vet:
        notes = notes.filter(Note.veterinarian == vet)

    # --- Filtre date début ---
    if start:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        start_dt = start_dt.replace(tzinfo=TZ_PARIS)
        notes = notes.filter(Note.created_at >= start_dt)

    # --- Filtre date fin ---
    if end:
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        # fin de journée locale : 23:59:59
        end_dt = end_dt.replace(hour=23, minute=59, second=59, tzinfo=TZ_PARIS)
        notes = notes.filter(Note.created_at <= end_dt)

    # --- Tri date desc ---
    notes = notes.order_by(Note.created_at.desc()).all()

    # --- Réponse JSON ---
    return jsonify([
    {
        "id": n.id,
        "cat_name": n.cat.name if n.cat else "",
        "cat_id": n.cat_id,
        "content": n.content or "",
        "author": n.author or "—",
        "veterinarian": n.veterinarian or None,
        "file": n.file_name,
        
        # Création formatée Europe/Paris
        "created_at": n.created_at.astimezone(TZ_PARIS).strftime("%d/%m/%Y %H:%M"),

        # Modification formatée Europe/Paris (si disponible)
        "updated_at": n.updated_at.astimezone(TZ_PARIS).strftime("%d/%m/%Y %H:%M")
                     if n.updated_at else None,
    }
    for n in notes
])



@app.route("/api/search_cats_for_notes")
def search_cats_for_notes():
    q = (request.args.get("q") or "").strip().lower()

    cats = Cat.query
    if q:
        cats = cats.filter(Cat.name.ilike(f"%{q}%"))

    cats = cats.order_by(Cat.name.asc()).limit(15).all()

    return jsonify([
        {"id": c.id, "name": c.name}
        for c in cats
    ])
    
# ============================================================
# GESTION VACCINS + EMPLOYÉS
# ============================================================

@app.route("/gestion/vaccins", methods=["GET", "POST"])
@site_protected
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
@site_protected
def supprimer_vaccin(vaccine_id):
    v = VaccineType.query.get_or_404(vaccine_id)
    db.session.delete(v)
    db.session.commit()
    return redirect(url_for("gestion_vaccins"))


@app.route("/gestion/employes", methods=["GET", "POST"])
@site_protected
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
@site_protected
def supprimer_employe(employee_id):
    emp = Employee.query.get_or_404(employee_id)

    try:
        db.session.delete(emp)
        db.session.commit()
        flash("Employé supprimé.", "success")
    except:
        flash("Erreur lors de la suppression.", "danger")

    return redirect(url_for("gestion_employes"))


@app.route("/gestion/veterinaires", methods=["GET", "POST"])
@site_protected
def gestion_veterinaires():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            db.session.add(Veterinarian(name=name))
            db.session.commit()
        return redirect(url_for("gestion_veterinaires"))

    veterinarians = Veterinarian.query.order_by(Veterinarian.name).all()
    return render_template("manage_veterinarians.html", veterinarians=veterinarians)

@app.route('/manage_tasks', methods=['GET', 'POST'])
@site_protected
def manage_tasks():
    # TRAITEMENT FORMULAIRE
    if request.method == 'POST':
        action = request.form.get('action')

        # ➕ Création d'un type de tâche
        if action == "create":
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()

            if not name:
                flash("Le nom de la tâche est obligatoire.", "danger")
                return redirect(url_for('manage_tasks'))

            existing = TaskType.query.filter_by(name=name).first()
            if existing:
                flash("Ce type de tâche existe déjà.", "warning")
                return redirect(url_for('manage_tasks'))

            new_type = TaskType(name=name, description=description)
            db.session.add(new_type)
            db.session.commit()
            flash("Type de tâche ajouté.", "success")
            return redirect(url_for('manage_tasks'))

        # ✏️ Mise à jour
        if action == "update":
            task_id = request.form.get('task_type_id')
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            is_active = True if request.form.get('is_active') == "on" else False

            t = TaskType.query.get(task_id)
            if not t:
                flash("Type de tâche introuvable.", "danger")
                return redirect(url_for('manage_tasks'))

            if not name:
                flash("Le nom est obligatoire.", "danger")
                return redirect(url_for('manage_tasks'))

            t.name = name
            t.description = description
            t.is_active = is_active
            db.session.commit()

            flash("Type de tâche mis à jour.", "success")
            return redirect(url_for('manage_tasks'))

        # ❌ Suppression
        if action == "delete":
            task_id = request.form.get('task_type_id')
            t = TaskType.query.get(task_id)

            if not t:
                flash("Type de tâche introuvable.", "danger")
                return redirect(url_for('manage_tasks'))

            db.session.delete(t)
            db.session.commit()
            flash("Type de tâche supprimé.", "success")
            return redirect(url_for('manage_tasks'))

    # PAGE (GET)
    task_types = TaskType.query.order_by(TaskType.name).all()
    return render_template('manage_tasks.html', task_types=task_types)

@app.route('/cats/<int:cat_id>/tasks/create', methods=['POST'])
@site_protected
def create_cat_task(cat_id):
    cat = Cat.query.get_or_404(cat_id)

    task_type_id = request.form.get('task_type_id')
    note = request.form.get('note', '').strip()

    if not task_type_id:
        flash("Merci de sélectionner un type de tâche.", "danger")
        return redirect(url_for('cat_detail', cat_id=cat.id) + "?tab=tasks")

    task_type = TaskType.query.get(task_type_id)
    if not task_type or not task_type.is_active:
        flash("Type de tâche invalide ou désactivé.", "danger")
        return redirect(url_for('cat_detail', cat_id=cat.id) + "?tab=tasks")

    # Date d'échéance
    due_date_str = request.form.get("due_date")
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except:
            due_date = None

    new_task = CatTask(
        cat_id=cat.id,
        task_type_id=task_type_id,
        note=note,
        due_date=due_date
    )

    db.session.add(new_task)
    db.session.commit()

    flash("Tâche ajoutée pour ce chat.", "success")
    return redirect(url_for('cat_detail', cat_id=cat.id) + "?tab=tasks")


@app.route('/cats/<int:cat_id>/tasks/<int:task_id>/toggle', methods=['POST'])
@site_protected
def toggle_cat_task(cat_id, task_id):
    task = CatTask.query.get_or_404(task_id)

    if task.cat_id != cat_id:
        flash("Action invalide.", "danger")
        return redirect(url_for('cat_detail', cat_id=cat_id) + "?tab=tasks")

    # ❌ Si la tâche est déjà faite → pas de retour en arrière
    if task.is_done:
        flash("Cette tâche est déjà complétée.", "warning")
        return redirect(url_for('cat_detail', cat_id=cat_id) + "?tab=tasks")

    done_by = request.form.get("done_by")
    if not done_by:
        flash("Merci de sélectionner un employé.", "danger")
        return redirect(url_for('cat_detail', cat_id=cat_id) + "?tab=tasks")

    # Mise à jour
    task.is_done = True
    task.done_by = done_by
    task.done_at = datetime.now(TZ_PARIS)

    db.session.commit()
    flash("Tâche marquée comme effectuée.", "success")

    return redirect(url_for('cat_detail', cat_id=cat_id) + "?tab=tasks")

@app.route('/cats/<int:cat_id>/tasks/<int:task_id>/delete', methods=['POST'])
@site_protected
def delete_cat_task(cat_id, task_id):
    task = CatTask.query.get_or_404(task_id)

    if task.cat_id != cat_id:
        flash("Action invalide.", "danger")
        return redirect(url_for('cat_detail', cat_id=cat_id) + "?tab=tasks")

    db.session.delete(task)
    db.session.commit()

    flash("Tâche supprimée.", "success")
    return redirect(url_for('cat_detail', cat_id=cat_id) + "?tab=tasks")

@app.route("/gestion/veterinaires/supprimer/<int:veterinarian_id>", methods=["POST"])
@site_protected
def supprimer_veterinaire(veterinarian_id):
    v = Veterinarian.query.get_or_404(veterinarian_id)
    db.session.delete(v)
    db.session.commit()
    return redirect(url_for("gestion_veterinaires"))
    
@app.route("/api/cats", methods=["GET", "POST"])
def api_cats():

    # 🔐 Sécurité API : l’utilisateur doit être loggé
    if session.get("authenticated") is not True:
        return jsonify({"error": "unauthorized"}), 401

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

        db.session.add(
    Cat(
        name=name,
        birthdate=birthdate,
        status=request.form.get("status") or None,
        photo_filename=filename,
        identification_number=request.form.get("identification_number") or None,
        entry_date=datetime.strptime(request.form["entry_date"], "%Y-%m-%d").date() if request.form.get("entry_date") else None,
        gender=request.form.get("gender") or None,
        )
    )

        db.session.commit()
        return redirect(url_for("cats"))

    # ---- GET LIST ----
    q = (request.args.get("q") or "").strip()
    query = Cat.query
    if q:
        query = query.filter(Cat.name.ilike(f"%{q}%"))
    cats = query.order_by(Cat.name).all()

    out = []
    for c in cats:

        # --- Nombre de tâches en cours ---
        tasks_todo = CatTask.query.filter_by(cat_id=c.id, is_done=False).count()

                # --- Dernière modification (note / tâche / vaccin) ---
        last_dates = []

        if c.notes:
            last_dates.append(max(
                n.created_at.astimezone(TZ_PARIS) for n in c.notes
            ))

        if c.tasks:
            last_dates.append(max(
                t.created_at.astimezone(TZ_PARIS) for t in c.tasks
            ))

        if c.vaccinations:
            last_dates.append(max(
                datetime.combine(v.date, datetime.min.time()).replace(tzinfo=TZ_PARIS)
                for v in c.vaccinations
            ))

        last_update = "—"
        if last_dates:
            last_update = max(last_dates).strftime("%d/%m/%Y %H:%M")


        out.append({
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "birthdate": c.birthdate.isoformat() if c.birthdate else None,
            "age_human": age_text(c.birthdate),
            "photo": c.photo_filename,

            "fiv": c.fiv,
            "need_vet": c.need_vet,
            "tasks_todo": tasks_todo,
            "last_update": last_update,
        })

    return jsonify(out)



# ============================================================
# HEALTHCHECK (Render)
# ============================================================

@app.route("/health")
@site_protected
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        return {"status": "ok"}, 200
    except Exception as e:
        return {"status": "db_error", "detail": str(e)}, 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
