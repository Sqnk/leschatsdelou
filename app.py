import os
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from werkzeug.utils import secure_filename

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
    fiv = db.Column(db.Boolean, default=False)   # 👈 NOUVELLE COLONNE

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
    author = db.Column(db.String(120))       # auteur de la note
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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
    
@app.template_filter("age")
def age_filter(d):
    return age_text(d)



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
    cols = [col["name"] for col in inspector.get_columns("appointment")]
    if "created_by" not in cols:
        print("➡️ Ajout de la colonne 'created_by' dans la table 'appointment'…")
        db.session.execute(db.text("ALTER TABLE appointment ADD COLUMN created_by VARCHAR(120)"))
        db.session.commit()
        print("✅ Colonne 'created_by' ajoutée.")


# ============================================================
# STATIC UPLOADS
# ============================================================
@app.route("/cats/<int:cat_id>/delete", methods=["POST"])
def delete_cat(cat_id):
    cat = Cat.query.get_or_404(cat_id)

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

    return redirect(url_for("recherche"))
    
@app.route("/notes/<int:note_id>/delete", methods=["POST"])
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
def appointment_edit(appointment_id):
    appt = Appointment.query.get_or_404(appointment_id)
    cats = Cat.query.order_by(Cat.name).all()
    employees = Employee.query.order_by(Employee.name).all()

    return render_template(
        "appointment_edit.html",
        appt=appt,
        cats=cats,
        employees=employees
    )
    
@app.route("/appointments/<int:appointment_id>/delete", methods=["POST"])
def appointment_delete(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)

    # Suppression des relations chats et employés
    AppointmentCat.query.filter_by(appointment_id=appointment_id).delete()
    AppointmentEmployee.query.filter_by(appointment_id=appointment_id).delete()

    db.session.delete(appointment)
    db.session.commit()

    return redirect(url_for("appointments_page"))

@app.route("/appointments/<int:appointment_id>/delete", methods=["POST"])
def delete_appointment(appointment_id):
    appt = Appointment.query.get_or_404(appointment_id)

    db.session.delete(appt)
    db.session.commit()

    return redirect(url_for("appointments"))

@app.route("/appointments/<int:appointment_id>/edit", methods=["POST"])
def appointment_update(appointment_id):
    appt = Appointment.query.get_or_404(appointment_id)

    # Update date + lieu
    date_str = request.form.get("date")
    if date_str:
        appt.date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M")

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

@app.route("/")
def index():
    return render_template("cats.html")


# -------------------- Helpers dashboard --------------------
def compute_vaccines_due(days: int = 30):
    """Retourne uniquement les vaccins en retard ou à venir dans X jours."""

    today = date.today()
    limit = today + timedelta(days=days)
    results = []

    vaccine_types = VaccineType.query.all()
    cats = Cat.query.all()

    for cat in cats:
        # Regroupe la dernière injection par type
        last_by_type = {}
        for v in cat.vaccinations:
            if v.date:
                vt = v.vaccine_type_id
                if vt not in last_by_type or v.date > last_by_type[vt]:
                    last_by_type[vt] = v.date

        for vt in vaccine_types:

            # si le chat n'a JAMAIS eu ce vaccin → on ignore
            if vt.id not in last_by_type:
                continue

            last_date = last_by_type[vt.id]
            next_due = last_date + timedelta(days=365)

            days_left = (next_due - today).days

            # vaccins en retard
            if next_due < today:
                results.append({
                    "cat": cat,
                    "vaccine": vt,
                    "last_date": last_date,
                    "next_due": next_due,
                    "days_left": days_left,
                    "status": "late"
                })
                continue

            # vaccins à faire dans X jours
            if today <= next_due <= limit:
                results.append({
                    "cat": cat,
                    "vaccine": vt,
                    "last_date": last_date,
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
def dashboard():

    # On utilise la fonction fiable
    vaccines_due = compute_vaccines_due(30)

    # Comptages
    vaccines_late_count = sum(1 for v in vaccines_due if v["status"] == "late")
    vaccines_due_count  = sum(1 for v in vaccines_due if v["status"] == "soon")

    stats = {
        "cats": Cat.query.count(),
        "appointments": Appointment.query.count(),
        "employees": Employee.query.count(),
    }

    return render_template(
        "dashboard.html",
        stats=stats,
        vaccines_due=vaccines_due,
        vaccines_late_count=vaccines_late_count,
        vaccines_due_count=vaccines_due_count,
        total_cats=stats["cats"],
        total_appointments=stats["appointments"],
        total_employees=stats["employees"],
    )




@app.route("/recherche")
def recherche():
    return render_template("search_cats.html", q="", cats=Cat.query.order_by(Cat.name).all())


@app.route("/calendrier")
def calendrier():
    return render_template("calendrier.html")


@app.route("/cats")
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


# ============================================================
# APPOINTMENTS (PAGE + CREATION)
# ============================================================

@app.route("/appointments")
def appointments_page():
    now = datetime.utcnow()

    upcoming = Appointment.query.filter(
        Appointment.date >= now
    ).order_by(Appointment.date).all()

    past = Appointment.query.filter(
        Appointment.date < now
    ).order_by(Appointment.date.desc()).all()

    cats = Cat.query.order_by(Cat.name).all()
    employees = Employee.query.order_by(Employee.name).all()
    veterinarians = Veterinarian.query.order_by(Veterinarian.name).all()

    return render_template(
        "appointments.html",
        upcoming=upcoming,
        past=past,
        cats=cats,
        employees=employees,
        veterinarians=veterinarians
    )



@app.route("/appointments/create", methods=["POST"])
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
        date=dt,
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


# -------------------- FullCalendar events --------------------

@app.route("/appointments_events")
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
def api_appointments():
    """Endpoint JSON détaillé pour le calendrier (FullCalendar du dashboard)."""
    events = []
    for a in Appointment.query.all():
        cats_str = ", ".join(ca.cat.name for ca in a.cats)
        emps_str = ", ".join(emp.employee.name for emp in a.employees)

        tooltip_lines = [
            a.date.strftime("%d/%m/%Y %H:%M"),
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
            "extendedProps": {
                "tooltip": tooltip,
                "cats": cats_str,
                "employees": emps_str,
                "location": a.location or "",
            },
            "url": url_for("appointments_page"),
        })

    return jsonify(events)


# ============================================================
# FICHE CHAT
# ============================================================

@app.route("/cats/<int:cat_id>")
def cat_detail(cat_id):
    c = Cat.query.get_or_404(cat_id)
    vaccines = VaccineType.query.order_by(VaccineType.name).all()
    vaccs = Vaccination.query.filter_by(cat_id=cat_id).order_by(Vaccination.date.desc()).all()
    notes = Note.query.filter_by(cat_id=cat_id).order_by(Note.created_at.desc()).all()
    employees = Employee.query.order_by(Employee.name).all()
    veterinarians = Veterinarian.query.order_by(Veterinarian.name).all()

    return render_template(
        "cat_detail.html",
        cat=c,
        vaccines=vaccines,
        vaccs=vaccs,
        notes=notes,
        employees=employees,
        veterinarians=veterinarians,
        age_text=age_text,
    )
@app.route("/cats/<int:cat_id>/update_status", methods=["POST"])
def update_cat_status(cat_id):
    cat = Cat.query.get_or_404(cat_id)

    # Mise à jour du statut
    new_status = request.form.get("status") or None
    cat.status = new_status

    # 🧬 Mise à jour FIV
    cat.fiv = "fiv" in request.form   # case cochée → True

    db.session.commit()
    return redirect(url_for("cat_detail", cat_id=cat_id))

@app.route("/cats/<int:cat_id>/vaccinations", methods=["POST"])
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
    # Vérifie que le chat existe
    _ = Cat.query.get_or_404(cat_id)

    # Récupération du contenu
    content = (request.form.get("content") or "").strip()

    # Auteur depuis la liste déroulante
    author = request.form.get("author")
    if author == "":
        author = None

    # Gestion fichier
    file = request.files.get("file")
    file_name = None
    if file and file.filename:
        fn = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], fn))
        file_name = fn

    # Ne rien enregistrer si tout est vide
    if not content and not file_name:
        return redirect(url_for("cat_detail", cat_id=cat_id))

    # Création de la note
    new_note = Note(
        cat_id=cat_id,
        content=content or None,
        file_name=file_name,
        author=author,
    )

    db.session.add(new_note)
    db.session.commit()

    return redirect(url_for("cat_detail", cat_id=cat_id))



# ============================================================
# RECHERCHE DE NOTES
# ============================================================

@app.route("/search_notes")
def search_notes():
    notes = Note.query.order_by(Note.created_at.desc()).all()
    employees = Employee.query.order_by(Employee.name).all()

    return render_template("search_notes.html", notes=notes, employees=employees)


@app.route("/api/search_notes")
def api_search_notes():
    q = (request.args.get("q") or "").strip().lower()
    cat_id = (request.args.get("cat") or "").strip()
    author = (request.args.get("author") or "").strip()
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

    # --- Filtre date début ---
    if start:
        notes = notes.filter(Note.created_at >= f"{start} 00:00:00")

    # --- Filtre date fin ---
    if end:
        notes = notes.filter(Note.created_at <= f"{end} 23:59:59")

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
            "file": n.file_name,
            "created_at": n.created_at.strftime("%d/%m/%Y %H:%M"),
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

@app.route("/gestion/veterinaires", methods=["GET", "POST"])
def gestion_veterinaires():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            db.session.add(Veterinarian(name=name))
            db.session.commit()
        return redirect(url_for("gestion_veterinaires"))

    veterinarians = Veterinarian.query.order_by(Veterinarian.name).all()
    return render_template("manage_veterinarians.html", veterinarians=veterinarians)


@app.route("/gestion/veterinaires/supprimer/<int:veterinarian_id>", methods=["POST"])
def supprimer_veterinaire(veterinarian_id):
    v = Veterinarian.query.get_or_404(veterinarian_id)
    db.session.delete(v)
    db.session.commit()
    return redirect(url_for("gestion_veterinaires"))
    
@app.route("/gestion/employes/supprimer/<int:employee_id>", methods=["POST"])
def supprimer_employe(employee_id):
    e = Employee.query.get_or_404(employee_id)
    db.session.delete(e)
    db.session.commit()
    return redirect(url_for("gestion_employes"))


# ============================================================
# API CATS (utilisée par la page /recherche)
# ============================================================

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

        db.session.add(
            Cat(
                name=name,
                birthdate=birthdate,
                status=request.form.get("status") or None,
                photo_filename=filename,
            )
        )
        db.session.commit()
        return redirect(url_for("cats"))

    q = (request.args.get("q") or "").strip()
    query = Cat.query
    if q:
        query = query.filter(Cat.name.ilike(f"%{q}%"))
    cats = query.order_by(Cat.name).all()

    return jsonify([
        {
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "birthdate": c.birthdate.isoformat() if c.birthdate else None,
            "age_human": age_text(c.birthdate),
            "photo": c.photo_filename,
        }
        for c in cats
    ])


# ============================================================
# HEALTHCHECK (Render)
# ============================================================

@app.route("/health")
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        return {"status": "ok"}, 200
    except Exception as e:
        return {"status": "db_error", "detail": str(e)}, 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
