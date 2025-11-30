import os
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, jsonify, session, send_file
from flask_sqlalchemy import SQLAlchemy
from dateutil.relativedelta import relativedelta
from sqlalchemy import inspect
from sqlalchemy import text
from sqlalchemy import func
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
class DewormingType(db.Model):
    __tablename__ = "deworming_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

    # 💡 tous les vermifuges de ce type
    dewormings = db.relationship(
        "Deworming",
        back_populates="deworming_type",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def __repr__(self):
        return f"<DewormingType {self.name}>"


class Cat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    birthdate = db.Column(db.Date)
    status = db.Column(db.String(50))
    photo_filename = db.Column(db.String(200))
    entry_reason = db.Column(db.String(100))
    exit_date = db.Column(db.Date)
    exit_reason = db.Column(db.String(100))

    identification_number = db.Column(db.String(120))          # 🔥 nouveau
    entry_date = db.Column(db.Date)                            # 🔥 nouveau
    gender = db.Column(db.String(20))                          # 🔥 ajouté aussi (M/F) car absent

    fiv = db.Column(db.Boolean, default=False)
    need_vet = db.Column(db.Boolean, default=False)

    vaccinations = db.relationship("Vaccination", backref="cat", lazy=True)
    notes = db.relationship("Note", backref="cat", lazy=True)
    appointments = db.relationship("AppointmentCat", back_populates="cat")
    tasks = db.relationship("CatTask", back_populates="cat", cascade="all, delete-orphan")
    dewormings = db.relationship(
    "Deworming",
    backref="cat",
    lazy=True,
    cascade="all, delete-orphan"
    )
    
class ActivityReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)

    # Entrées
    entries_abandon = db.Column(db.Integer, default=0)
    entries_return = db.Column(db.Integer, default=0)       # retours après placement
    entries_found = db.Column(db.Integer, default=0)
    entries_total = db.Column(db.Integer, default=0)
    count_start = db.Column(db.Integer, default=0)          # animaux en début de mois

    # Sorties
    exits_placed = db.Column(db.Integer, default=0)
    exits_returned_owner = db.Column(db.Integer, default=0)
    exits_deceased = db.Column(db.Integer, default=0)
    exits_escaped = db.Column(db.Integer, default=0)
    exits_transferred = db.Column(db.Integer, default=0)
    exits_total = db.Column(db.Integer, default=0)
    count_end = db.Column(db.Integer, default=0)            # animaux en fin de mois

    pdf_filename = db.Column(db.String(255))                # chemin du PDF sauvegardé
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(TZ_PARIS))
    updated_at = db.Column(db.DateTime)

class PurchaseOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_date = db.Column(db.Date, nullable=False, default=date.today)
    pdf_filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(TZ_PARIS))


class Weight(db.Model):
    __tablename__ = "weight"

    id = db.Column(db.Integer, primary_key=True)
    cat_id = db.Column(db.Integer, db.ForeignKey("cat.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    weight = db.Column(db.Float, nullable=False)

    cat = db.relationship("Cat", backref="weights")


# ================================
# DEWORMING BATCH (historique)
# ================================
class DewormingBatch(db.Model):
    __tablename__ = "deworming_batch"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(TZ_PARIS))

    items = db.relationship(
        "DewormingBatchItem",
        back_populates="batch",
        cascade="all, delete-orphan",
    )


class DewormingBatchItem(db.Model):
    __tablename__ = "deworming_batch_item"

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("deworming_batch.id"), nullable=False)
    cat_id = db.Column(db.Integer, db.ForeignKey("cat.id"), nullable=False)
    deworming_id = db.Column(db.Integer, db.ForeignKey("deworming.id"), nullable=True)
    weight_id = db.Column(db.Integer, db.ForeignKey("weight.id"), nullable=True)

    batch = db.relationship("DewormingBatch", back_populates="items")
    cat = db.relationship("Cat")
    deworming = db.relationship("Deworming")
    weight = db.relationship("Weight")

    
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
# --- FERMIFUGE MODEL ---
class Deworming(db.Model):   # traitement vermifuge
    id = db.Column(db.Integer, primary_key=True)
    cat_id = db.Column(db.Integer, db.ForeignKey("cat.id"), nullable=False)

    # 🔹 nouveau lien vers le type de vermifuge
    deworming_type_id = db.Column(
        db.Integer,
        db.ForeignKey("deworming_types.id"),
        nullable=True,
    )

    date = db.Column(db.Date, default=date.today)   # date d’administration
    done_by = db.Column(db.String(120))
    reaction = db.Column(db.String(255))
    note = db.Column(db.Text)                       # optionnel

    # relation vers le type
    deworming_type = db.relationship(
        "DewormingType",
        back_populates="dewormings",
        lazy=True,
    )

    

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

def count_cats_present_on(day: date) -> int:
    """
    Retourne combien de chats sont présents au refuge à une date donnée.
    Règles :
    - Inclus : chats dont entry_date <= day
    - Exclus : chats adoptés, en famille d'accueil ou décédés AVANT cette date
    """
    return Cat.query.filter(
        Cat.entry_date <= day,
        db.or_(
            Cat.exit_date.is_(None),
            Cat.exit_date > day
        ),
        Cat.status.notin_(["adopté", "décédé", "famille d'accueil"])
    ).count()

def compute_activity_stats(year: int, month: int):
    """
    Calcule les entrées / sorties / nb début / nb fin pour un mois donné,
    selon la logique comptable demandée :
      count_start + entries_total - exits_total = count_end
    """

    # Bornes du mois
    start_date = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    end_date = next_month - timedelta(days=1)

    # 🔥 1) Animaux en début de mois
    count_start = Cat.query.filter(
        Cat.entry_date < start_date,
        db.or_(Cat.exit_date.is_(None), Cat.exit_date >= start_date)
    ).count()

    # 🔥 2) Entrées pendant le mois
    cats_entries = Cat.query.filter(
        Cat.entry_date >= start_date,
        Cat.entry_date <= end_date
    ).all()

    entries_lists = {"abandon": [], "return": [], "found": []}

    for c in cats_entries:
        r = (c.entry_reason or "").lower()
        if "abandon" in r:
            entries_lists["abandon"].append(c)
        elif "retour" in r:
            entries_lists["return"].append(c)
        elif "trouv" in r:
            entries_lists["found"].append(c)

    entries_abandon = len(entries_lists["abandon"])
    entries_return = len(entries_lists["return"])
    entries_found = len(entries_lists["found"])
    entries_total = entries_abandon + entries_return + entries_found

    # 🔥 3) Sorties pendant le mois
    cats_exits = Cat.query.filter(
        Cat.exit_date >= start_date,
        Cat.exit_date <= end_date
    ).all()

    exits_lists = {
        "placed": [],
        "returned_owner": [],
        "deceased": [],
        "escaped": [],
        "transferred": [],
    }

    for c in cats_exits:
        r = (c.exit_reason or "").lower()
        if "plac" in r:
            exits_lists["placed"].append(c)
        elif "propri" in r:
            exits_lists["returned_owner"].append(c)
        elif "déc" in r or "dec" in r:
            exits_lists["deceased"].append(c)
        elif "échapp" in r or "echapp" in r:
            exits_lists["escaped"].append(c)
        elif "transfér" in r or "transfer" in r:
            exits_lists["transferred"].append(c)

    exits_placed = len(exits_lists["placed"])
    exits_returned_owner = len(exits_lists["returned_owner"])
    exits_deceased = len(exits_lists["deceased"])
    exits_escaped = len(exits_lists["escaped"])
    exits_transferred = len(exits_lists["transferred"])
    exits_total = (
        exits_placed +
        exits_returned_owner +
        exits_deceased +
        exits_escaped +
        exits_transferred
    )

    # 🔥 4) Animaux en fin de mois = FORMULE DEMANDÉE
    count_end = count_start + entries_total - exits_total

    counts = {
        "entries_abandon": entries_abandon,
        "entries_return": entries_return,
        "entries_found": entries_found,
        "entries_total": entries_total,

        "count_start": count_start,

        "exits_placed": exits_placed,
        "exits_returned_owner": exits_returned_owner,
        "exits_deceased": exits_deceased,
        "exits_escaped": exits_escaped,
        "exits_transferred": exits_transferred,
        "exits_total": exits_total,

        "count_end": count_end,
    }

    return {
        "counts": counts,
        "entries_lists": entries_lists,
        "exits_lists": exits_lists,
        "start_date": start_date,
        "end_date": end_date,
    }


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

@app.route("/edit_deworming_type/<int:type_id>", methods=["POST"])
@site_protected
def edit_deworming_type(type_id):
    dt = DewormingType.query.get_or_404(type_id)

    dt.name = request.form.get("name")
    dt.description = request.form.get("description")
    dt.is_active = True if request.form.get("is_active") == "on" else False

    db.session.commit()
    return redirect(url_for("manage_deworming"))

@app.route("/delete_deworming_type/<int:type_id>", methods=["POST"])
@site_protected
def delete_deworming_type(type_id):
    dt = DewormingType.query.get_or_404(type_id)

    db.session.delete(dt)
    db.session.commit()

    return redirect(url_for("manage_deworming"))

@app.route("/add_deworming_type", methods=["POST"])
@site_protected
def add_deworming_type():
    name = request.form.get("name")
    description = request.form.get("description")

    if name:
        new_type = DewormingType(name=name.strip(), description=description)
        db.session.add(new_type)
        db.session.commit()

    return redirect(url_for("manage_deworming"))
        
@app.route("/manage_deworming")
@site_protected
def manage_deworming():
    types = DewormingType.query.order_by(DewormingType.name.asc()).all()
    return render_template("manage_deworming.html", types=types)

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
    if "deworming_types" not in inspector.get_table_names():
        print("➡️ Création de la table deworming_types…")
        DewormingType.__table__.create(db.engine)
        print("✅ Table deworming_types créée.")

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
    existing_tables = inspector.get_table_names()

    if "deworming_batch" not in existing_tables:
        DewormingBatch.__table__.create(db.engine)

    if "deworming_batch_item" not in existing_tables:
        DewormingBatchItem.__table__.create(db.engine)
        
with app.app_context():
    inspector = inspect(db.engine)
    if "activity_report" not in inspector.get_table_names():
        print("➡️ Création de la table activity_report…")
        ActivityReport.__table__.create(db.engine)
        print("✅ Table activity_report créée.")

with app.app_context():
    inspector = inspect(db.engine)
    if "purchase_order" not in inspector.get_table_names():
        print("➡️ Création de la table purchase_order…")
        PurchaseOrder.__table__.create(db.engine)
        print("✅ Table purchase_order créée.")

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

    # 🔹 nouveau : type de vermifuge
    if "deworming_type_id" not in cols:
        print("➡️ Ajout colonne deworming_type_id…")
        db.session.execute(db.text(
            "ALTER TABLE deworming ADD COLUMN deworming_type_id INTEGER "
            "REFERENCES deworming_types(id)"
        ))
        db.session.commit()
        print("✅ Colonne deworming_type_id ajoutée.")






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

with app.app_context():
    inspector = inspect(db.engine)
    cols = [col["name"] for col in inspector.get_columns("cat")]

    if "exit_date" not in cols:
        print("➡️ Ajout colonne exit_date…")
        db.session.execute(db.text("ALTER TABLE cat ADD COLUMN exit_date DATE"))
        db.session.commit()

    if "exit_reason" not in cols:
        print("➡️ Ajout colonne exit_reason…")
        db.session.execute(db.text("ALTER TABLE cat ADD COLUMN exit_reason VARCHAR(100)"))
        db.session.commit()
        
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
    cols = [col["name"] for col in inspector.get_columns("cat")]

    if "entry_reason" not in cols:
        print("➡️ Ajout colonne entry_reason…")
        db.session.execute(db.text(
            "ALTER TABLE cat ADD COLUMN entry_reason VARCHAR(100)"
        ))
        db.session.commit()
        print("✅ Colonne entry_reason ajoutée.")
    
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
  

# -------------------- Helpers dashboard (vermifuge groupé) --------------------
def compute_deworming_group_reminder():
    """
    Rappel global de vermifuge groupé pour le dashboard.

    - On prend la DERNIÈRE date de vermifuge enregistrée (table Deworming),
      qui correspond au dernier vermifuge groupé (les lots sont regroupés par date).
    - Prochain vermifuge recommandé : ~ 2 mois plus tard (60 jours)
    - Statut :
        * 'late'  si la date recommandée est dépassée
        * 'soon'  si on est dans les 7 jours avant
        * 'ok'    sinon
    """
    # Dernière date de vermifuge (tous chats confondus)
    last_date = db.session.query(func.max(Deworming.date)).scalar()

    if not last_date:
        # Aucun vermifuge saisi → rien à afficher
        return None

    today = date.today()
    # Prochain vermifuge recommandé : environ 2 mois après
    next_due = last_date + timedelta(days=60)

    # Nombre de jours restants avant la date recommandée
    days_left = (next_due - today).days

    if days_left < 0:
        status = "late"
    elif days_left <= 7:
        status = "soon"
    else:
        status = "ok"

    return {
        "last_date": last_date,
        "next_due": next_due,
        "status": status,
        "days_left": days_left,
    }




  
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

    return redirect(url_for("cat_detail", cat_id=note.cat_id, tab="notes"))


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

    return redirect(url_for("cat_detail", cat_id=cat_id, tab="notes"))

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

@app.post("/cats/<int:cat_id>/weights/<int:weight_id>/delete")
def delete_weight(cat_id, weight_id):
    w = Weight.query.get_or_404(weight_id)
    db.session.delete(w)
    db.session.commit()
    return redirect(url_for("cat_detail", cat_id=cat_id, tab="weights"))

@app.post("/cats/<int:cat_id>/exit")
@site_protected
def cat_exit(cat_id):
    cat = Cat.query.get_or_404(cat_id)

    exit_date = request.form.get("exit_date")
    exit_reason = request.form.get("exit_reason")

    if exit_date:
        cat.exit_date = datetime.strptime(exit_date, "%Y-%m-%d").date()

    cat.exit_reason = exit_reason

    # 🔥 Mise à jour automatique du statut selon la sortie
    if exit_reason == "Décédé":
        cat.status = "décédé"
    elif exit_reason in ("Placé", "Rendu au propriétaire"):
        cat.status = "adopté"

    db.session.commit()
    flash("Sortie enregistrée.", "success")
    return redirect(url_for("cat_detail", cat_id=cat_id))

@app.post("/cats/<int:cat_id>/cancel_exit")
@site_protected
def cat_cancel_exit(cat_id):
    """Annule la sortie : enlève date + raison, et remet le chat en 'présent'."""
    cat = Cat.query.get_or_404(cat_id)

    # On supprime les infos de sortie
    cat.exit_date = None
    cat.exit_reason = None

    # Si le statut avait été mis automatiquement, on le remet sur "normal"
    if cat.status in ("adopté", "décédé"):
        cat.status = "normal"

    db.session.commit()
    flash("Sortie annulée, le chat est de nouveau marqué comme présent.", "success")
    return redirect(url_for("cat_detail", cat_id=cat_id))

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
    cats = Cat.query.filter(
        db.or_(
            Cat.exit_date.is_(None),
            Cat.status == "famille d'accueil"
        ),
        Cat.status.notin_(["adopté", "décédé"])
    ).all()

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


def compute_dewormings_due(days: int = 7):
    """
    Rappels de vermifuge PAR CHAT :
    - 'late'  : vermifuge en retard
    - 'soon'  : vermifuge à faire dans <= days jours
    """
    today = date.today()
    limit = today + timedelta(days=days)
    results = []

    # Chats présents ou en famille d'accueil, hors adoptés/décédés
    cats = Cat.query.filter(
        db.or_(
            Cat.exit_date.is_(None),
            Cat.status == "famille d'accueil"
        ),
        Cat.status.notin_(["adopté", "décédé"])
    ).all()

    for cat in cats:
        if not cat.dewormings:
            continue

        # Dernier vermifuge de ce chat
        last_deworm = max(cat.dewormings, key=lambda d: d.date)

        # Rappel toutes les 8 semaines (2 mois)
        next_due = last_deworm.date + relativedelta(months=2)
        days_left = (next_due - today).days

        # En retard
        if next_due < today:
            results.append({
                "cat": cat,
                "last_date": last_deworm.date,
                "next_due": next_due,
                "days_left": days_left,
                "status": "late",
            })
            continue

        # À venir dans X jours
        if today <= next_due <= limit:
            results.append({
                "cat": cat,
                "last_date": last_deworm.date,
                "next_due": next_due,
                "days_left": days_left,
                "status": "soon",
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

    # ------------------ Vermifuges (individuels) ------------------
    dewormings_due = compute_dewormings_due(7)
    deworm_late_count = sum(1 for d in dewormings_due if d["status"] == "late")
    deworm_due_count  = sum(1 for d in dewormings_due if d["status"] == "soon")

    # ------------------ Vermifuges (groupé) ------------------
    deworm_group = compute_deworming_group_reminder()

    # ------------------ Stats ------------------
    stats = {
        "cats": Cat.query.filter(
            Cat.exit_date.is_(None),
            Cat.status.notin_(["adopté", "décédé", "famille d'accueil"])
        ).count(),
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
        # cartes de gauche = par chat
        deworm_late_count=deworm_late_count,
        deworm_due_count=deworm_due_count,
        # bloc central = groupé
        deworm_group=deworm_group,
        # on passe aussi la liste détaillée pour un futur hover
        dewormings_due=dewormings_due,

        # --- contenu pour le dashboard ---
        cats=Cat.query.filter(
            Cat.exit_date.is_(None),
            Cat.status.notin_(["adopté", "décédé", "famille d'accueil"])
        ).order_by(Cat.name).all(),
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

    q = (request.args.get("q") or "").strip()
    ident = (request.args.get("ident") or "").strip()
    status = request.args.get("status")
    exit_filter = request.args.get("exit")
    exit_reason = (request.args.get("exit_reason") or "").strip()
    tasks_active = request.args.get("tasks_active")
    no_vacc = request.args.get("no_vacc")
    no_deworm = request.args.get("no_deworm")
    entry_min = request.args.get("entry_min")
    entry_max = request.args.get("entry_max")

    query = Cat.query
    
    only_exited = request.args.get("only_exited") == "1"

    if only_exited:
        query = query.filter(Cat.exit_date.isnot(None))
    # 🔎 recherche texte
    if q:
        query = query.filter(Cat.name.ilike(f"%{q}%"))

    # 🔎 numéro d'identification
    if ident:
        query = query.filter(Cat.identification_number.ilike(f"%{ident}%"))

    # 🔎 statut
    if status == "present":
        query = query.filter(
            db.or_(Cat.exit_date.is_(None), Cat.status == "famille d'accueil")
        )
    elif status in ("adopté", "décédé", "famille"):
        if status == "famille":
            query = query.filter(Cat.status == "famille d'accueil")
        else:
            query = query.filter(Cat.status == status)

    # 🔎 sortie
    if exit_filter == "yes":
        query = query.filter(Cat.exit_date.isnot(None))
    elif exit_filter == "no":
        query = query.filter(Cat.exit_date.is_(None))

    # 🔎 raison de sortie
    if exit_reason:
        query = query.filter(Cat.exit_reason.ilike(f"%{exit_reason}%"))

    # 🔎 date entrée min
    if entry_min:
        query = query.filter(Cat.entry_date >= entry_min)

    # date entrée max
    if entry_max:
        query = query.filter(Cat.entry_date <= entry_max)
    
    exit_only = request.args.get("exit_only")

    if exit_only == "yes":
        query = query.filter(Cat.exit_date.isnot(None))
    elif exit_only == "no":
        query = query.filter(Cat.exit_date.is_(None))

    # 🔎 sans vaccinations
    if no_vacc:
        query = query.filter(~Cat.vaccinations.any())

    # 🔎 sans vermifuges
    if no_deworm:
        query = query.filter(~Cat.dewormings.any())

    # 🔎 chats avec tâches actives
    if tasks_active:
        query = query.filter(Cat.tasks.any(CatTask.is_done == False))

    cats = query.order_by(Cat.name).all()

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

    # Historique des rapports d'activité déjà générés
    reports = ActivityReport.query.order_by(
        ActivityReport.year.desc(),
        ActivityReport.month.desc()
    ).all()
    
     # Historique des bons de commande
    orders = PurchaseOrder.query.order_by(
        PurchaseOrder.order_date.desc(),
        PurchaseOrder.created_at.desc()
    ).all()

    return render_template(
        "documents.html",
        products=products,
        reports=reports,
        orders=orders
    )

@app.route("/documents/activity_report/generate", methods=["POST"])
@site_protected
def generate_activity_report():
    import io
    import os
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import black, blue, white
    from reportlab.lib.enums import TA_RIGHT, TA_LEFT
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from datetime import datetime

    # ---------------------------------------------------------
    # UTILITAIRE : texte multi-ligne centré verticalement
    # ---------------------------------------------------------
    def draw_multiline_text(canvas, text, x, y, width, height,
                            align=TA_LEFT, font_name="Helvetica",
                            font_size=12, color=black):
        styles = getSampleStyleSheet()
        style = styles['Normal']
        style.fontName = font_name
        style.fontSize = font_size
        style.textColor = color
        style.alignment = align

        p = Paragraph(text, style)
        p_width, p_height = p.wrapOn(canvas, width, height)
        y_offset = (height - p_height) / 2
        p.drawOn(canvas, x, y + y_offset)

    # ---------------------------------------------------------
    # RÉCUP PARAMÈTRES
    # ---------------------------------------------------------
    try:
        year = int(request.form.get("year"))
        month = int(request.form.get("month"))
    except:
        year = datetime.now().year
        month = datetime.now().month

    fields = [
        "entries_abandon", "entries_return", "entries_found", "entries_total",
        "count_start",
        "exits_placed", "exits_returned_owner", "exits_deceased",
        "exits_escaped", "exits_transferred", "exits_total", "count_end",
    ]
    counts = {f: int(request.form.get(f, 0) or 0) for f in fields}

    # ---------------------------------------------------------
    # ESPÈCES (autres que chats) — cohérent avec confirmation.html
    # ---------------------------------------------------------
    species_start = []
    for i in range(1, 5):
        name = request.form.get(f"species{i}_name", "").strip()
        count = request.form.get(f"species{i}_count", "").strip()
        if name and count and count != "0":
            species_start.append({"name": name, "count": int(count)})

    species_end = []
    for i in range(1, 5):
        name = request.form.get(f"species{i}_name_end", "").strip()
        count = request.form.get(f"species{i}_count_end", "").strip()
        if name and count and count != "0":
            species_end.append({"name": name, "count": int(count)})

    if not species_end:
        species_end = list(species_start)

    # chats début / fin
    chats_start = counts.get("count_start", 0)
    chats_end = counts.get("count_end", 0)

    # totaux animaux (chats + autres)
    total_start = chats_start + sum(sp["count"] for sp in species_start)
    total_end = chats_end + sum(sp["count"] for sp in species_end)

    # ---------------------------------------------------------
    # MOIS FORMATÉ
    # ---------------------------------------------------------
    month_names = {
        1: "JANVIER", 2: "FÉVRIER", 3: "MARS", 4: "AVRIL",
        5: "MAI", 6: "JUIN", 7: "JUILLET", 8: "AOÛT",
        9: "SEPTEMBRE", 10: "OCTOBRE", 11: "NOVEMBRE", 12: "DÉCEMBRE",
    }
    title_month = f"{month_names.get(month, '').upper()} {year}"

    # ---------------------------------------------------------
    # INIT PDF
    # ---------------------------------------------------------
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margin_left = 40
    usable_width = width - margin_left - 40

    # ---------------------------------------------------------
    # LOGO
    # ---------------------------------------------------------
    logo_path = os.path.join(app.static_folder, "logo_faa.png")
    logo_w = 150
    logo_h = 100
    logo_x = margin_left
    logo_y = height - 10 - logo_h

    if os.path.exists(logo_path):
        c.drawImage(
            logo_path, logo_x, logo_y,
            width=logo_w, height=logo_h,
            preserveAspectRatio=True, mask="auto"
        )

    # ---------------------------------------------------------
    # TITRE
    # ---------------------------------------------------------
    title_y = height - 150
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, title_y, "RAPPORT D’ACTIVITÉ DES ANIMAUX")

    c.setFont("Helvetica", 13)
    c.drawCentredString(width / 2, title_y - 25, "Maison de retraite de Louveciennes")

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, title_y - 55, title_month)

    # ---------------------------------------------------------
    # TABLEAU
    # ---------------------------------------------------------
    line_h_std = 35
    header_h = 40

    table_width = usable_width * 0.8
    table_x = margin_left + (usable_width - table_width) / 2
    col_split_x = table_x + table_width / 2
    col_width = table_width / 2

    label_width = col_width - 50
    left_x_label = table_x + 12
    right_x_label = col_split_x + 12

    header_top_y = title_y - 120

    # bandeau ENTRÉES / SORTIES
    c.setFillColor(blue)
    c.rect(table_x, header_top_y - header_h, table_width, header_h, stroke=0, fill=1)

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(left_x_label, header_top_y - header_h + 12, "ENTRÉES")
    c.drawString(right_x_label, header_top_y - header_h + 12, "SORTIES")

    # Ligne verticale
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    c.line(col_split_x, header_top_y - header_h, col_split_x, header_top_y - header_h - 5)

    # ---------------------------------------------------------
    # LIGNES TABLEAU
    # ---------------------------------------------------------
    entries_rows = [
        ("Abandons", "entries_abandon"),
        ("Retours après placement", "entries_return"),
        ("Trouvés", "entries_found"),
        ("", None),
        ("", None),
        ("", None),
        ("Total des entrées", "entries_total"),
        ("Animaux en début de mois", "count_start"),
    ]

    sorties_rows = [
        ("Placés", "exits_placed"),
        ("Rendus à leur propriétaire", "exits_returned_owner"),
        ("Décédés", "exits_deceased"),
        ("Échappés", "exits_escaped"),
        ("Transférés vers un autre établissement", "exits_transferred"),
        ("", None),
        ("Total des sorties", "exits_total"),
        ("Animaux en fin de mois", "count_end"),
    ]

    y_current = header_top_y - header_h

    # hauteur dynamique dernière ligne
    max_species = max(len(species_start), len(species_end))
    last_row_lines = 2 + max_species   # Animaux + Chats + (espèces)
    last_row_height = 40 + last_row_lines * 16

    for i in range(8):
        row_h = last_row_height if i == 7 else line_h_std
        line_y = y_current - row_h
        is_total_row = i >= 6

        if is_total_row:
            c.setFillColor(blue)
            c.rect(table_x, line_y, table_width, row_h, stroke=0, fill=1)
            text_color = white
            font_style = "Helvetica-Bold"
            font_size = 11
        else:
            text_color = black
            font_style = "Helvetica"
            font_size = 12

        # dernière ligne → block multi-lignes
        if i == 7:
            left_text = f"Animaux en début de mois : {total_start}"
            left_text += f"<br/>Chats : {chats_start}"
            for sp in species_start:
                left_text += f"<br/>{sp['name']} : {sp['count']}"

            right_text = f"Animaux en fin de mois : {total_end}"
            right_text += f"<br/>Chats : {chats_end}"
            for sp in species_end:
                right_text += f"<br/>{sp['name']} : {sp['count']}"

            draw_multiline_text(c, left_text, left_x_label, line_y,
                                col_width - 20, row_h, TA_LEFT,
                                font_style, font_size, text_color)
            draw_multiline_text(c, right_text, right_x_label, line_y,
                                col_width - 20, row_h, TA_LEFT,
                                font_style, font_size, text_color)
        else:
            # lignes normales
            e_label, e_key = entries_rows[i]
            if e_label:
                draw_multiline_text(
                    c, f"{e_label} :", left_x_label, line_y,
                    label_width, row_h, TA_LEFT,
                    font_style, font_size, text_color
                )
                val = counts.get(e_key, 0) if e_key else ""
                draw_multiline_text(
                    c, str(val), col_split_x - 50, line_y,
                    40, row_h, TA_RIGHT,
                    font_style, font_size, text_color
                )

            s_label, s_key = sorties_rows[i]
            if s_label:
                draw_multiline_text(
                    c, f"{s_label} :", right_x_label, line_y,
                    label_width, row_h, TA_LEFT,
                    font_style, font_size, text_color
                )
                val = counts.get(s_key, 0) if s_key else ""
                draw_multiline_text(
                    c, str(val), table_x + table_width - 50,
                    line_y, 40, row_h, TA_RIGHT,
                    font_style, font_size, text_color
                )

        # traits
        c.setStrokeColor(black)
        c.setLineWidth(0.8 if is_total_row else 0.4)
        c.line(table_x, line_y, table_x + table_width, line_y)
        c.line(col_split_x, y_current, col_split_x, line_y)

        y_current = line_y

    # cadre extérieur
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    c.rect(table_x, y_current, table_width,
           header_top_y - y_current - header_h, stroke=1, fill=0)
    c.line(col_split_x, y_current, col_split_x, header_top_y - header_h)

    # ---------------------------------------------------------
    c.showPage()
    c.save()
    buffer.seek(0)

    # ---------------------------------------------------------
    # SAVE + DB
    # ---------------------------------------------------------
    reports_folder = os.path.join(app.config["UPLOAD_FOLDER"], "reports")
    os.makedirs(reports_folder, exist_ok=True)

    filename = f"Rapport d'activité {month_names[month].capitalize()} {year}.pdf"
    file_path = os.path.join(reports_folder, filename)

    with open(file_path, "wb") as f:
        f.write(buffer.getvalue())

    report = ActivityReport.query.filter_by(year=year, month=month).first()
    if not report:
        report = ActivityReport(year=year, month=month)
        db.session.add(report)

    for k, v in counts.items():
        setattr(report, k, v)

    report.pdf_filename = filename
    report.updated_at = datetime.now(TZ_PARIS)
    if not report.created_at:
        report.created_at = datetime.now(TZ_PARIS)

    db.session.commit()

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf"
    )










 
@app.route("/documents/activity_report/<int:year>/<int:month>")
@site_protected
def activity_report_download(year, month):
    report = ActivityReport.query.filter_by(year=year, month=month).first_or_404()

    reports_folder = os.path.join(app.config["UPLOAD_FOLDER"], "reports")
    file_path = os.path.join(reports_folder, report.pdf_filename or "")

    if not os.path.exists(file_path):
        flash("Le fichier PDF de ce rapport est introuvable sur le serveur.", "danger")
        return redirect(url_for("documents"))

    return send_file(file_path, as_attachment=False)

@app.post("/documents/activity_report/confirm")
@site_protected
def activity_report_confirm():
    year = int(request.form.get("year"))
    month = int(request.form.get("month"))

    # ----------------------------
    # Champs numériques standard
    # ----------------------------
    fields = [
        "entries_abandon",
        "entries_return",
        "entries_found",
        "entries_total",
        "count_start",
        "exits_placed",
        "exits_returned_owner",
        "exits_deceased",
        "exits_escaped",
        "exits_transferred",
        "exits_total",
        "count_end",
    ]

    values = {}
    for f in fields:
        try:
            values[f] = int(request.form.get(f, 0))
        except:
            values[f] = 0

    # ----------------------------
    # NOUVELLE LOGIQUE ESPÈCES
    # ----------------------------
    species = []
    species_names = []
    species_counts = []

    for i in range(1, 5):
        name = (request.form.get(f"type{i}_name") or "").strip()
        count_raw = request.form.get(f"type{i}_count", "").strip()

        try:
            count = int(count_raw)
        except:
            count = 0

        # toujours stocker dans counts pour les hidden
        values[f"type{i}_name"] = name
        values[f"type{i}_count"] = count

        if name != "" and count > 0:
            species.append({"name": name, "count": count})
            species_names.append(name)
            species_counts.append(count)

    # ----------------------------
    # Envoi vers la page confirm
    # ----------------------------
    return render_template(
        "activity_report_confirm.html",
        year=year,
        month=month,
        counts=values,
        species=species,
        species_names=species_names,   # <<< AJOUTÉ
        species_counts=species_counts  # <<< AJOUTÉ
    )


@app.post("/documents/activity_report/details")
@site_protected
def activity_report_details():
    try:
        year = int(request.form.get("year"))
        month = int(request.form.get("month"))
    except (TypeError, ValueError):
        flash("Mois ou année invalides.", "danger")
        return redirect(url_for("documents"))

    data = compute_activity_stats(year, month)

    return render_template(
        "activity_report_details.html",
        year=year,
        month=month,
        counts=data["counts"],
        entries_lists=data["entries_lists"],
        exits_lists=data["exits_lists"]
    )

@app.route("/documents/generate_pdf", methods=["POST"])
def generate_pdf():
    import io
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from datetime import datetime
    from flask import send_file

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

    # TABLEAU
    start_x = 30
    start_y = height - 220

    col_ref = 80
    col_label = 300
    col_qte = 50
    line_h = 20

    table_width = col_ref + col_label + col_qte

    # En-tête
    c.setFont("Helvetica-Bold", 11)
    c.rect(start_x, start_y, table_width, line_h)

    # traits verticaux en-tête
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

    # aucune nouvelle page ici
    c.save()
    buffer.seek(0)


     # ---------- Sauvegarde sur le disque + enregistrement en base ----------
    orders_folder = os.path.join(app.config["UPLOAD_FOLDER"], "orders")
    os.makedirs(orders_folder, exist_ok=True)

    now_ts = datetime.now(TZ_PARIS)
    filename = f"bon_de_commande_{now_ts.strftime('%Y%m%d_%H%M%S')}.pdf"
    display_name = f"Bon de commande IDF {now_ts.strftime('%d.%m.%y')}.pdf"
    file_path = os.path.join(orders_folder, filename)

    # On écrit le PDF sur le disque
    with open(file_path, "wb") as f:
        f.write(buffer.getvalue())

    # Enregistrement en base pour l'historique
    po = PurchaseOrder(
        order_date=now_ts.date(),
        pdf_filename=filename,
        created_at=now_ts
    )
    db.session.add(po)
    db.session.commit()

    # On renvoie aussi le PDF au navigateur avec le bon nom
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=display_name,
        mimetype="application/pdf"
    )

@app.route("/documents/orders/<int:order_id>")
@site_protected
def order_download(order_id):
    order = PurchaseOrder.query.get_or_404(order_id)

    orders_folder = os.path.join(app.config["UPLOAD_FOLDER"], "orders")
    file_path = os.path.join(orders_folder, order.pdf_filename or "")

    if not os.path.exists(file_path):
        flash("Le fichier PDF de ce bon de commande est introuvable sur le serveur.", "danger")
        return redirect(url_for("documents"))

    return send_file(file_path, as_attachment=False)


@app.post("/documents/orders/<int:order_id>/delete")
@site_protected
def order_delete(order_id):
    order = PurchaseOrder.query.get_or_404(order_id)

    orders_folder = os.path.join(app.config["UPLOAD_FOLDER"], "orders")
    file_path = os.path.join(orders_folder, order.pdf_filename or "")

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except:
            pass

    db.session.delete(order)
    db.session.commit()
    flash("Bon de commande supprimé de l'historique.", "success")
    return redirect(url_for("documents"))





    
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

            "backgroundColor": "#FFA500",
            "borderColor": "#FFA500",

            "extendedProps": {
                "tooltip": tooltip,
                "location": g.title,
                "note": g.note or None,
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

    # 🔹 tous les types de vermifuge actifs pour les listes déroulantes
    deworming_types = DewormingType.query \
        .filter_by(is_active=True) \
        .order_by(DewormingType.name.asc()) \
        .all()

    cat = Cat.query.get_or_404(cat_id)
    notes = Note.query.filter_by(cat_id=cat_id).order_by(Note.created_at.desc()).all()
    active_tab = request.args.get("tab", "infos")

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
        deworming_types=deworming_types,   # ⬅️ nouveau
        active_tab=active_tab,
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
    # Vérifie que le chat existe
    _ = Cat.query.get_or_404(cat_id)

    # Date
    date_str = request.form.get("date")
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        d = date.today()

    # Type de vermifuge (nouvelle logique)
    deworming_type_id = request.form.get("deworming_type_id", type=int)
    reaction = request.form.get("reaction") or None

    new_d = Deworming(
        cat_id=cat_id,
        date=d,
        deworming_type_id=deworming_type_id,
        reaction=reaction,
        # done_by / note restent possibles en base mais on ne les touche pas ici
    )

    db.session.add(new_d)
    db.session.commit()

    return redirect(url_for("cat_detail", cat_id=cat_id) + "?tab=vermifuges")

@app.route("/deworming_batch", methods=["GET", "POST"])
@site_protected
def deworming_batch():
    today = date.today()

    # ⚙️ Chats éligibles pour le vermifuge groupé
    # (tu peux garder exactement ta logique actuelle si elle est différente)
    cats = (
        Cat.query
        .filter(Cat.exit_date.is_(None))  # présents (non sortis)
        .order_by(Cat.name.asc())
        .all()
    )

    # ⚙️ Types de vermifuge actifs
    deworming_types = (
        DewormingType.query
        .filter_by(is_active=True)
        .order_by(DewormingType.name.asc())
        .all()
    )

    # ================== POST : création des lignes Vermifuge + Poids ==================
    if request.method == "POST":
        # IMPORTANT : même name que dans le template : name="deworming_date"
        date_str = request.form.get("deworming_date")
        if date_str:
            try:
                deworm_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                deworm_date = today
        else:
            deworm_date = today

        created_any = False

        # On récupère les IDs de chats envoyés par le formulaire (hidden "cat_ids")
        raw_ids = request.form.getlist("cat_ids")
        cat_ids = []
        for cid in raw_ids:
            try:
                cat_ids.append(int(cid))
            except ValueError:
                continue

        for cid in cat_ids:
            # On ne traite que les chats cochés
            if not request.form.get(f"selected_{cid}"):
                continue

            type_id = request.form.get(f"deworming_type_{cid}")
            weight_raw = request.form.get(f"weight_{cid}")
            reaction = (request.form.get(f"reaction_{cid}") or "").strip() or None

            # Si rien n’est saisi pour ce chat → on le saute
            if not (type_id or weight_raw or reaction):
                continue

            # 🔹 Vermifuge
            if type_id:
                try:
                    type_id_int = int(type_id)
                except ValueError:
                    type_id_int = None

                if type_id_int:
                    new_dw = Deworming(
                        cat_id=cid,
                        date=deworm_date,
                        deworming_type_id=type_id_int,
                        reaction=reaction,
                    )
                    db.session.add(new_dw)
                    created_any = True

            # 🔹 Poids
            if weight_raw:
                try:
                    weight_val = float(weight_raw.replace(",", "."))
                except ValueError:
                    weight_val = None

                if weight_val is not None:
                    new_w = Weight(
                        cat_id=cid,
                        date=deworm_date,
                        weight=weight_val,
                    )
                    db.session.add(new_w)
                    created_any = True

            # Cas où il n’y a que la réaction (pas de type / pas de poids)
            if reaction and not type_id and not weight_raw:
                new_dw = Deworming(
                    cat_id=cid,
                    date=deworm_date,
                    reaction=reaction,
                )
                db.session.add(new_dw)
                created_any = True

        if created_any:
            db.session.commit()
            flash("Vermifuge groupé enregistré.", "success")
        else:
            flash("Aucune ligne valide n'a été sélectionnée.", "warning")

        return redirect(url_for("deworming_batch"))

    # ================== GET : dernière pesée + historique groupé ==================

    # Dernier poids par chat (pour l’affichage "Dernier poids" dans le tableau)
    last_weights_sub = (
        db.session.query(
            Weight.cat_id,
            func.max(Weight.date).label("last_date"),
        )
        .group_by(Weight.cat_id)
        .subquery()
    )

    last_weights = (
        db.session.query(Weight.cat_id, Weight.weight)
        .join(
            last_weights_sub,
            (Weight.cat_id == last_weights_sub.c.cat_id)
            & (Weight.date == last_weights_sub.c.last_date),
        )
        .all()
    )

    last_weights_map = {cid: w for cid, w in last_weights}

    # Historique groupé par date
    history_rows = (
        db.session.query(
            Deworming.date.label("date"),
            Cat.name.label("cat_name"),
            Cat.identification_number.label("identification_number"),
            Deworming.reaction.label("reaction"),
            DewormingType.name.label("type_name"),
            Weight.weight.label("weight"),
        )
        .join(Cat, Cat.id == Deworming.cat_id)
        .outerjoin(
            DewormingType,
            DewormingType.id == Deworming.deworming_type_id,
        )
        .outerjoin(
            Weight,
            (Weight.cat_id == Deworming.cat_id)
            & (Weight.date == Deworming.date),
        )
        .order_by(Deworming.date.desc(), Cat.name.asc())
        .all()
    )

    deworming_history = {}
    for row in history_rows:
        d = row.date
        if d not in deworming_history:
            deworming_history[d] = []
        deworming_history[d].append(row)

    return render_template(
        "deworming_batch.html",
        cats=cats,
        deworming_types=deworming_types,
        today=today,
        last_weights_map=last_weights_map,
        deworming_history=deworming_history,
    )


@app.route("/delete_deworming_batch", methods=["POST"])
@site_protected
def delete_deworming_batch():
    date_str = request.form.get("date")
    if not date_str:
        flash("Date manquante pour la suppression.", "danger")
        return redirect(url_for("deworming_batch"))

    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        flash("Date invalide pour la suppression.", "danger")
        return redirect(url_for("deworming_batch"))

    # On récupère les dewormings du jour pour connaître les chats concernés
    dewormings = Deworming.query.filter_by(date=target_date).all()
    cat_ids = {dw.cat_id for dw in dewormings}

    # Suppression de toutes les lignes de vermifuge à cette date
    Deworming.query.filter_by(date=target_date).delete(synchronize_session=False)

    # Suppression des poids à cette date pour ces chats
    if cat_ids:
        Weight.query.filter(
            Weight.date == target_date,
            Weight.cat_id.in_(list(cat_ids))
        ).delete(synchronize_session=False)

    db.session.commit()

    flash(
        f"Entrées poids et vermifuge supprimées pour {len(cat_ids)} chat(s) à la date du {target_date.strftime('%d/%m/%Y')}.",
        "success",
    )
    return redirect(url_for("deworming_batch"))

@app.route("/cats/<int:cat_id>/deworming/<int:dw_id>/edit", methods=["POST"])
@site_protected
def edit_deworming(cat_id, dw_id):
    d = Deworming.query.get_or_404(dw_id)

    # Date
    date_str = request.form.get("date")
    if date_str:
        d.date = datetime.strptime(date_str, "%Y-%m-%d").date()

    # Type de vermifuge
    deworming_type_id = request.form.get("deworming_type_id", type=int)
    if deworming_type_id:
        d.deworming_type_id = deworming_type_id
    else:
        d.deworming_type_id = None

    # Réaction
    d.reaction = request.form.get("reaction") or None

    db.session.commit()
    return redirect(url_for("cat_detail", cat_id=cat_id) + "?tab=vermifuges")

@app.route("/cats/<int:cat_id>/deworming/<int:dw_id>/delete", methods=["POST"])
@site_protected
def delete_deworming(cat_id, dw_id):
    d = Deworming.query.get_or_404(dw_id)
    db.session.delete(d)
    db.session.commit()
    return redirect(url_for("cat_detail", cat_id=cat_id) + "?tab=vermifuges")

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
        return redirect(url_for("cat_detail", cat_id=cat_id, tab="vaccins"))

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
    return redirect(url_for("cat_detail", cat_id=cat_id, tab="vaccins"))

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

    return redirect(url_for("cat_detail", cat_id=cat_id, tab="notes"))




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

    # ------------------ CRÉATION (POST) ------------------
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
                entry_date=datetime.strptime(request.form["entry_date"], "%Y-%m-%d").date()
                if request.form.get("entry_date")
                else None,
                entry_reason=request.form.get("entry_reason"),
                gender=request.form.get("gender") or None,
            )
        )

        db.session.commit()
        return redirect(url_for("cats"))

    # ------------------ LISTE / FILTRES (GET) ------------------
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    present = (request.args.get("present") or "").strip()          # "", "present", "exited"
    exit_reason = (request.args.get("exit_reason") or "").strip()
    has_task = (request.args.get("has_task") or "").strip()        # "1" si coché
    no_vacc = (request.args.get("no_vacc") or "").strip()          # "1" si coché
    no_deworm = (request.args.get("no_deworm") or "").strip()      # "1" si coché
    ident = (request.args.get("ident") or "").strip()
    entry_start = (request.args.get("entry_start") or "").strip()
    entry_end = (request.args.get("entry_end") or "").strip()

    query = Cat.query

    # Nom
    if q:
        query = query.filter(Cat.name.ilike(f"%{q}%"))

    # Numéro d'identification
    if ident:
        query = query.filter(Cat.identification_number.ilike(f"%{ident}%"))

    # Statut exact
    if status:
        query = query.filter(Cat.status == status)

    # Présent / sorti
    if present == "present":
        # Chats présents au refuge
        query = query.filter(
            Cat.exit_date.is_(None),
            Cat.status.notin_(["adopté", "décédé", "famille d'accueil"]),
        )
    elif present == "exited":
        # Chats sortis (avec une date de sortie)
        query = query.filter(Cat.exit_date.is_not(None))

    # Raison de sortie (contient le texte sélectionné)
    if exit_reason:
        query = query.filter(Cat.exit_reason.ilike(f"%{exit_reason}%"))

    # Date d'entrée
    if entry_start:
        try:
            d_start = datetime.strptime(entry_start, "%Y-%m-%d").date()
            query = query.filter(Cat.entry_date >= d_start)
        except Exception:
            pass

    if entry_end:
        try:
            d_end = datetime.strptime(entry_end, "%Y-%m-%d").date()
            query = query.filter(Cat.entry_date <= d_end)
        except Exception:
            pass

    # Avec au moins une tâche active
    if has_task == "1":
        query = (
            query.join(CatTask, CatTask.cat_id == Cat.id)
            .filter(CatTask.is_done.is_(False))
        )

    # Sans vaccination
    if no_vacc == "1":
        query = query.filter(~Cat.vaccinations.any())

    # Sans vermifuge
    if no_deworm == "1":
        query = query.filter(~Cat.dewormings.any())

    # éviter les doublons si join sur CatTask
    query = query.distinct().order_by(Cat.name)

    cats = query.all()

    out = []
    for c in cats:

        # --- Nombre de tâches en cours ---
        tasks_todo = CatTask.query.filter_by(cat_id=c.id, is_done=False).count()

        # --- Dernière modification (note / tâche / vaccin) ---
        last_dates = []

        if c.notes:
            last_dates.append(
                max(n.created_at.astimezone(TZ_PARIS) for n in c.notes)
            )

        if c.tasks:
            last_dates.append(
                max(t.created_at.astimezone(TZ_PARIS) for t in c.tasks)
            )

        if c.vaccinations:
            last_dates.append(
                max(
                    datetime.combine(v.date, datetime.min.time()).replace(
                        tzinfo=TZ_PARIS
                    )
                    for v in c.vaccinations
                )
            )

        last_update = "—"
        if last_dates:
            last_update = max(last_dates).strftime("%d/%m/%Y %H:%M")

        out.append(
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "birthdate": c.birthdate.isoformat() if c.birthdate else None,
                "age_human": age_text(c.birthdate),
                "photo": c.photo_filename,
                "has_exit": True if c.exit_date else False,
                "has_exit": True if c.exit_date else False,
                "exit_date": c.exit_date.isoformat() if c.exit_date else None,
                "exit_reason": c.exit_reason or None,
                "fiv": c.fiv,
                "need_vet": c.need_vet,
                "tasks_todo": tasks_todo,
                "last_update": last_update,
            }
        )

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
