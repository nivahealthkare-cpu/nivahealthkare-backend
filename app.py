from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user,
    login_required, current_user
)
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime, time
import pandas as pd
from flask import send_file
import tempfile
from flask import Flask, request, jsonify
import razorpay
import os
from dotenv import load_dotenv
import requests

load_dotenv()

TELEGRAM_BOT_TOKEN="8741305117:AAE_hYCgmbZtD9vuM-N5QzDglNrXmUVEbME"
TELEGRAM_CHAT_ID="8222983508"


RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))





def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def send_telegram_notification(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram Error:", e)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn



ADMIN_EMAIL = "admin@niva.com"
ADMIN_PASSWORD = "admin123"   # change later

# ---------------- CONFIG ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

print("FLASK IS USING DB:", DB_PATH)


app = Flask(__name__)

# ✅ Enable CORS for /api/* routes, allow requests from your frontend port
CORS(app)


app.secret_key = "niva-health-kare"
app.secret_key = 'niva-health-kare-secret'


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ---------------- USER MODEL ----------------
class User(UserMixin):
    def __init__(self, id, name, role):
        self.id = id
        self.name = name
        self.role = role


USERS = {
    "admin@niva.com": User(1, "Admin", "admin")
}


@login_manager.user_loader
def load_user(user_id):

    # 1️⃣ ADMIN (from USERS dict)
    for user in USERS.values():
        if str(user.id) == str(user_id):
            return user

    # 2️⃣ WORKER (from DATABASE)
    conn = get_db()
    worker = conn.execute(
        "SELECT id, username FROM workers WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    if worker:
        return User(worker["id"], worker["username"], "worker")

    return None


# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role")

        # ---------- ADMIN LOGIN ----------
        if role == "admin":
            email = request.form.get("email")
            password = request.form.get("password")

            if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
                user = User(1, "Admin", "admin")


                login_user(user)
                return redirect(url_for("admin_dashboard"))


        # ---------- WORKER LOGIN ----------
        if role == "worker":
            username = request.form.get("email")  # same input field
            password = request.form.get("password")

            conn = get_db()
            worker = conn.execute(
                "SELECT * FROM workers WHERE username = ?",
                (username,)
            ).fetchone()
            conn.close()

            if worker and check_password_hash(worker["password_hash"], password):
                user = User(worker["id"], worker["username"], "worker")
                login_user(user)
                return redirect(url_for("worker_dashboard"))

        return render_template("login.html", error="Invalid login")

    return render_template("login.html")





# ---------------- WORKER DASHBOARD ----------------
@app.route("/worker/dashboard")
@login_required
def worker_dashboard():
    if current_user.role != "worker":
        return redirect(url_for("admin_dashboard"))

    stats = {
        "total_leads": 0,
        "today_appointments": 0,
        "pending_tasks": 0,
        "bills_today": 0,
    }

    return render_template(
        "worker_dashboard.html",
        user=current_user,
        stats=stats
    )

# ---------------- WEB LEADS ----------------
@app.route("/worker/leads", methods=["GET", "POST"])
@login_required
def worker_leads():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("""
            INSERT INTO web_leads 
            (name, mobile, email, service, message, address, payment_type, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["name"],
            request.form["mobile"],
            request.form["email"],
            request.form["service"],
            request.form["message"],
            request.form.get("address"),
            request.form.get("payment_type", "Pending"),
            request.form.get("status", "New")
        ))
        conn.commit()

    # ✅ ALWAYS fetch leads (for both GET and POST)
    cursor.execute("""
        SELECT 
            id,
            name,
            mobile,
            message,
            email,
            service,
            address,
            payment_type,
            status
        FROM web_leads
        ORDER BY created_at DESC
    """)

    leads = cursor.fetchall()
    conn.close()

    return render_template("worker_leads.html", leads=leads)


@app.route('/lead-details/<int:lead_id>')
@login_required
def lead_details(lead_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM web_leads WHERE id = ?",
        (lead_id,)
    )
    lead = cursor.fetchone()
    conn.close()

    if not lead:
        return {"error": "Lead not found"}, 404

    return {
        "name": lead["name"],
        "email": lead["email"],
        "message": lead["message"],
        "payment_id": lead["razorpay_payment_id"]
    }



@app.route("/worker/appointments", methods=["GET", "POST"])
@login_required
def worker_appointments():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("""
            INSERT INTO appointments
            (name, mobile, email, service, address, message, payment, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form.get("name"),
            request.form.get("mobile"),
            request.form.get("email"),
            request.form.get("service"),
            request.form.get("address"),
            request.form.get("message"),
            request.form.get("payment", "Pending"),
            request.form.get("status", "Scheduled")
        ))

        conn.commit()
        conn.close()
        return redirect(url_for("worker_appointments"))

    cursor.execute("""
        SELECT *
        FROM appointments
        ORDER BY id DESC
    """)
    appointments = cursor.fetchall()
    conn.close()

    return render_template(
        "worker_appointments.html",
        appointments=appointments
    )
# ---------------- WORKER TODAY TASKS ----------------
@app.route("/worker/tasks", methods=["GET", "POST"])
@login_required
def worker_tasks():
    if current_user.role != "worker":
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Mark task as completed
    if request.method == "POST":
        task_id = request.form.get("task_id")
        cursor.execute("""
            UPDATE tasks
            SET status = 'Completed'
            WHERE id = ? AND assigned_to = ?
        """, (task_id, current_user.id))
        conn.commit()

    # Fetch today's tasks for this worker
    cursor.execute("""
        SELECT *
        FROM tasks
        WHERE assigned_to = ?
          AND task_date = DATE('now')
        ORDER BY id DESC
    """, (current_user.id,))

    tasks = cursor.fetchall()
    conn.close()

    return render_template("worker_tasks.html", tasks=tasks)


@app.route('/worker/hrms')
def worker_hrms():
    return render_template('worker_hrms.html')


from pytz import timezone

@app.route('/worker/hrms/attendance', methods=['GET', 'POST'])
@login_required
def worker_attendance():

    if current_user.role != "worker":
        return redirect(url_for('login'))

    # Indian Time (IST)
    ist = timezone("Asia/Kolkata")
    now = datetime.now(ist)

    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M:%S")

    late_limit = time(10, 15)

    message = None
    can_mark = True

    conn = get_db()
    cursor = conn.cursor()

    # 1️⃣ Check if already marked today
    already_marked = cursor.execute("""
        SELECT id FROM worker_attendance
        WHERE worker_id=? AND date=?
    """, (current_user.id, today)).fetchone()

    if already_marked:
        can_mark = False
        message = "✅ Attendance already marked for today"

    else:

        # 2️⃣ Show time message
        if now.time() > late_limit:
            message = f"⚠ You are late. Current time: {current_time}"
        else:
            message = f"✅ On time. Current time: {current_time}"

    # 3️⃣ Mark attendance
    if request.method == "POST" and can_mark:

        status = "Present"

        if now.time() > late_limit:
            status = "Late"

        cursor.execute("""
            INSERT INTO worker_attendance
            (worker_id, date, time, status)
            VALUES (?, ?, ?, ?)
        """, (current_user.id, today, current_time, status))

        conn.commit()

        message = f"✅ Attendance marked successfully at {current_time}"
        can_mark = False

    conn.close()

    return render_template(
        "worker_hrms_attendance.html",
        message=message,
        can_mark=can_mark
    )

@app.route('/worker/hrms/attendance/history')
@login_required
def worker_attendance_history():
    if current_user.role != "worker":
        return redirect(url_for('login'))

    conn = get_db()
    records = conn.execute("""
        SELECT date, time, status
        FROM worker_attendance
        WHERE worker_id = ?
        ORDER BY date DESC
    """, (current_user.id,)).fetchall()
    conn.close()

    return render_template(
        'worker_attendance_history.html',
        records=records
    )


@app.route('/worker/hrms/leave', methods=['GET', 'POST'])
@login_required
def worker_leave():
    if current_user.role != "worker":
        return redirect(url_for('login'))

    message = None

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # SUBMIT LEAVE
    if request.method == "POST":
        from_date = request.form["from_date"]
        to_date = request.form["to_date"]
        subject = request.form["subject"]
        reason = request.form["reason"]

        cursor.execute("""
            INSERT INTO worker_leaves
            (worker_id, from_date, to_date, subject, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (
            current_user.id,
            from_date,
            to_date,
            subject,
            reason
        ))

        conn.commit()
        message = "✅ Leave request submitted. Waiting for approval."

    # FETCH WORKER LEAVES (VERY IMPORTANT)
    cursor.execute("""
        SELECT from_date, to_date, subject, reason, status, applied_at
        FROM worker_leaves
        WHERE worker_id = ?
        ORDER BY id DESC
    """, (current_user.id,))

    leaves = cursor.fetchall()
    conn.close()

    return render_template(
        "worker_hrms_leave.html",
        message=message,
        leaves=leaves
    )


@app.route('/worker/hrms/payslip', methods=['GET', 'POST'])
@login_required
def worker_payslip():
    if current_user.role != "worker":
        return redirect(url_for('login'))

    # last 3 months only
    today = datetime.today()
    months = []
    for i in range(3):
        m = today.replace(day=1)
        m = m.month - i
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        months.append(f"{y}-{str(m).zfill(2)}")

    message = None

    if request.method == "POST":
        month = request.form["month"]

        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        slip = cursor.execute("""
            SELECT * FROM salary_payments
            WHERE worker_id=? AND month=?
        """, (current_user.id, month)).fetchone()

        conn.close()

        if not slip:
            message = "❌ Payslip not available for selected month"
        else:
            return redirect(
                url_for('download_worker_payslip', slip_id=slip["id"])
            )

    return render_template(
        "worker_hrms_payslip.html",
        months=months,
        message=message,
        user=current_user
    )

@app.route('/worker/hrms/contact', methods=['GET', 'POST'])
@login_required
def worker_hr_contact():
    if current_user.role != "worker":
        return redirect(url_for('login'))

    message = None
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":
        subject = request.form["subject"]
        body = request.form["message"]
        file = request.files.get("attachment")

        filename = None
        if file and file.filename:
            filename = secure_filename(file.filename)
            os.makedirs("uploads/hr", exist_ok=True)
            file.save(os.path.join("uploads/hr", filename))

        cursor.execute("""
            INSERT INTO hr_messages (worker_id, subject, message, attachment)
            VALUES (?, ?, ?, ?)
        """, (current_user.id, subject, body, filename))

        conn.commit()
        message = "✅ Message sent to HR. Status: Pending"

    # FETCH WORKER MESSAGES
    cursor.execute("""
        SELECT subject, message, reply, status, created_at
        FROM hr_messages
        WHERE worker_id = ?
        ORDER BY created_at DESC
    """, (current_user.id,))

    messages = cursor.fetchall()
    conn.close()

    return render_template(
        "worker_hrms_contact.html",
        message=message,
        messages=messages
    )



# ---------------- ADMIN DASHBOARD ----------------
@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    return render_template("admin_dashboard.html", user=current_user)
# ---------------- ADMIN TASKS ----------------
@app.route("/admin/tasks", methods=["GET", "POST"])
@login_required
def admin_tasks():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # FETCH WORKERS
    workers = cursor.execute("""
        SELECT id, username
        FROM workers
        ORDER BY username
    """).fetchall()

    # ADD TASK
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        assigned_to = request.form.get("assigned_to")

        cursor.execute("""
            INSERT INTO tasks (title, description, assigned_to, task_date)
            VALUES (?, ?, ?, DATE('now'))
        """, (title, description, assigned_to))

        conn.commit()
        conn.close()
        return redirect(url_for("admin_tasks"))

    # FETCH TASKS
    tasks = cursor.execute("""
        SELECT 
            t.id,
            t.title,
            t.description,
            t.status,
            t.task_date,
            w.username AS worker_name
        FROM tasks t
        LEFT JOIN workers w ON w.id = t.assigned_to
        ORDER BY t.id DESC
    """).fetchall()

    conn.close()
    return render_template("admin_tasks.html", workers=workers, tasks=tasks)


# ---------------- ADMIN LEADS ----------------
@app.route("/admin/leads")
@login_required
def admin_leads():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    leads = conn.execute("""
        SELECT *
        FROM web_leads
        ORDER BY id DESC
    """).fetchall()

    conn.close()
    return render_template("admin_leads.html", leads=leads)

@app.route("/admin/leads/edit/<int:lead_id>", methods=["GET", "POST"])
@login_required
def edit_lead(lead_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if request.method == "POST":
        conn.execute("""
            UPDATE web_leads
            SET name=?, mobile=?, email=?, message=?, service=?, address=?, status=?, payment_type=?
            WHERE id=?
        """, (
            request.form["name"],
            request.form["mobile"],
            request.form["email"],
            request.form["message"],
            request.form["service"],
            request.form["address"],
            request.form["status"],
            request.form["payment_type"],
            lead_id
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("admin_leads"))

    lead = conn.execute(
        "SELECT * FROM web_leads WHERE id=?",
        (lead_id,)
    ).fetchone()

    conn.close()
    return render_template("edit_lead.html", lead=lead)

@app.route("/admin/leads/delete/<int:lead_id>", methods=["POST"])
@login_required
def delete_lead(lead_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM web_leads WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_leads"))

# ---------------- ADMIN APPOINTMENTS ----------------
@app.route("/admin/appointments", methods=["GET", "POST"])
@login_required
def admin_appointments():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ADD APPOINTMENT
    if request.method == "POST":
        name = request.form["name"]
        mobile = request.form["mobile"]
        email = request.form.get("email")
        service = request.form.get("service")
        address = request.form.get("address")
        payment = request.form.get("payment")
        status = request.form.get("status")

        cursor.execute("""
            INSERT INTO appointments
            (name, mobile, email, service, address, payment, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, mobile, email, service, address, payment, status))

        conn.commit()
        conn.close()
        return redirect(url_for("admin_appointments"))

    # FETCH APPOINTMENTS
    cursor.execute("""
        SELECT *
        FROM appointments
        ORDER BY id DESC
    """)
    appointments = cursor.fetchall()

    conn.close()
    return render_template("admin_appointments.html", appointments=appointments)

# ---------------- EDIT APPOINTMENT ----------------
@app.route("/admin/appointments/edit/<int:id>", methods=["GET", "POST"])
@login_required
def admin_edit_appointment(id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("""
            UPDATE appointments
            SET name=?, mobile=?, email=?, service=?, address=?, payment=?, status=?
            WHERE id=?
        """, (
            request.form["name"],
            request.form["mobile"],
            request.form.get("email"),
            request.form.get("service"),
            request.form.get("address"),
            request.form.get("payment"),
            request.form.get("status"),
            id
        ))

        conn.commit()
        conn.close()
        return redirect(url_for("admin_appointments"))

    cursor.execute("SELECT * FROM appointments WHERE id=?", (id,))
    appointment = cursor.fetchone()

    conn.close()
    return render_template("admin_edit_appointment.html", appointment=appointment)

# ---------------- DELETE APPOINTMENT ----------------
@app.route("/admin/appointments/delete/<int:id>")
@login_required
def admin_delete_appointment(id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM appointments WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_appointments"))



# ---------------- ADMIN WORKERS ----------------
@app.route("/admin/workers")
@login_required
def admin_workers():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    conn = get_db()
    workers = conn.execute("""
        SELECT id, username, created_at
        FROM workers
        ORDER BY id DESC
    """).fetchall()
    conn.close()

    return render_template("admin_workers.html", workers=workers)


@app.route("/admin/workers/add", methods=["POST"])
@login_required
def admin_add_worker():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    username = request.form["username"]
    password = request.form["password"]

    password_hash = generate_password_hash(password)

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO workers (username, password_hash)
            VALUES (?, ?)
        """, (username, password_hash))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()

    return redirect(url_for("admin_workers"))


@app.route("/admin/workers/delete/<int:worker_id>")
@login_required
def admin_delete_worker(worker_id):
    if current_user.role != "admin":
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_workers"))


@app.route("/admin/workers/reset/<int:worker_id>", methods=["POST"])
@login_required
def admin_reset_worker_password(worker_id):
    if current_user.role != "admin":
        return redirect(url_for("login"))

    new_password = request.form["new_password"]
    password_hash = generate_password_hash(new_password)

    conn = get_db()
    conn.execute("""
        UPDATE workers
        SET password_hash = ?
        WHERE id = ?
    """, (password_hash, worker_id))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_workers"))




# ---------------- ADMIN HRMS ----------------
@app.route("/admin/hrms")
@login_required
def admin_hrms():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    return render_template("admin_hrms.html")


@app.route("/admin/hrms/attendance", methods=["GET"])
@login_required
def admin_attendance():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    conn = get_db()

    # 🔹 Attendance open / close status
    attendance_status = conn.execute(
        "SELECT is_open FROM attendance_control WHERE id = 1"
    ).fetchone()[0]

    # 🔹 Fetch workers (for dropdown)
    workers = conn.execute("""
        SELECT id, username
        FROM workers
        ORDER BY username
    """).fetchall()

    # 🔹 Filters (from URL)
    worker_id = request.args.get("worker_id", "")
    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")

    # 🔹 Base query
    query = """
        SELECT 
            wa.id,
            w.username,
            wa.date,
            wa.time,
            wa.status
        FROM worker_attendance wa
        JOIN workers w ON w.id = wa.worker_id
        WHERE 1 = 1
    """
    params = []

    # 🔹 Apply filters safely
    if worker_id:
        query += " AND wa.worker_id = ?"
        params.append(worker_id)

    if from_date:
        query += " AND wa.date >= ?"
        params.append(from_date)

    if to_date:
        query += " AND wa.date <= ?"
        params.append(to_date)

    query += " ORDER BY wa.date DESC, wa.time DESC"

    records = conn.execute(query, params).fetchall()
    conn.close()

    return render_template(
        "admin_attendance.html",
        workers=workers,
        records=records,
        attendance_status=attendance_status,
        selected_worker=worker_id,
        from_date=from_date,
        to_date=to_date
    )

@app.route("/admin/hrms/attendance/update", methods=["POST"])
@login_required
def admin_attendance_update():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    attendance_id = request.form.get("attendance_id")
    status = request.form.get("status")

    conn = get_db()
    conn.execute("""
        UPDATE worker_attendance
        SET status = ?
        WHERE id = ?
    """, (status, attendance_id))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_attendance"))


@app.route("/admin/hrms/attendance/export")
@login_required
def export_attendance():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    worker_id = request.args.get("worker_id", "")
    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")

    conn = get_db()

    query = """
        SELECT 
            w.username,
            wa.date,
            wa.status
        FROM worker_attendance wa
        JOIN workers w ON w.id = wa.worker_id
        WHERE 1 = 1
    """
    params = []

    if worker_id:
        query += " AND wa.worker_id = ?"
        params.append(worker_id)

    if from_date:
        query += " AND wa.date >= ?"
        params.append(from_date)

    if to_date:
        query += " AND wa.date <= ?"
        params.append(to_date)

    query += " ORDER BY w.username, wa.date"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    import pandas as pd

    df = pd.DataFrame(rows, columns=[
        "Worker Name",
        "Date",
        "Status"
    ])

    file_path = "attendance_sheet.xlsx"
    df.to_excel(file_path, index=False)

    return send_file(file_path, as_attachment=True)





@app.route("/admin/hrms/leaves", methods=["GET", "POST"])
@login_required
def admin_leaves():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # UPDATE STATUS
    if request.method == "POST":
        leave_id = request.form.get("leave_id")
        status = request.form.get("status")

        cursor.execute("""
            UPDATE worker_leaves
            SET status = ?
            WHERE id = ?
        """, (status, leave_id))

        conn.commit()

    # FETCH LEAVES
    leaves = cursor.execute("""
        SELECT
            l.id,
            w.username,
            l.subject,
            l.from_date,
            l.to_date,
            l.reason,
            l.status,
            l.applied_at
        FROM worker_leaves l
        JOIN workers w ON w.id = l.worker_id
        ORDER BY l.id DESC
    """).fetchall()

    conn.close()

    return render_template("admin_leaves.html", leaves=leaves)


  # ---------------- SALARY SETTINGS ----------------
@app.route("/admin/hrms/salary-settings", methods=["GET", "POST"])
@login_required
def admin_salary_settings():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    conn = get_db()

    # SAVE / UPDATE SALARY
    if request.method == "POST":
        worker_id = request.form["worker_id"]
        salary_type = request.form["salary_type"]
        amount = request.form["amount"]
        working_days = request.form.get("working_days", 26)

        existing = conn.execute("""
            SELECT id FROM salary_settings WHERE worker_id = ?
        """, (worker_id,)).fetchone()

        if existing:
            conn.execute("""
                UPDATE salary_settings
                SET salary_type=?, amount=?, working_days=?
                WHERE worker_id=?
            """, (salary_type, amount, working_days, worker_id))
        else:
            conn.execute("""
                INSERT INTO salary_settings
                (worker_id, salary_type, amount, working_days)
                VALUES (?, ?, ?, ?)
            """, (worker_id, salary_type, amount, working_days))

        conn.commit()

    workers = conn.execute("SELECT id, username FROM workers").fetchall()

    settings = conn.execute("""
        SELECT s.*, w.username
        FROM salary_settings s
        JOIN workers w ON w.id = s.worker_id
    """).fetchall()

    conn.close()

    return render_template(
        "admin_salary_settings.html",
        workers=workers,
        settings=settings
    )


# ---------------- SALARY CALCULATION ----------------
@app.route("/admin/hrms/salary-calculation", methods=["GET", "POST"])
@login_required
def admin_salary_calculation():
    conn = get_db_connection()

    workers = conn.execute(
        "SELECT id, username FROM workers"
    ).fetchall()


    result = None

    if request.method == "POST":
        worker_id = request.form["worker_id"]
        month = request.form["month"]  # YYYY-MM

        # Get salary
        salary = conn.execute(
            "SELECT monthly_salary FROM salary_settings WHERE worker_id=?",
            (worker_id,)
        ).fetchone()

        if salary:
            monthly_salary = salary["monthly_salary"]

            # Count present days
            present_days = conn.execute("""
                SELECT COUNT(*) 
                FROM attendance 
                WHERE worker_id=?
                  AND status='Present'
                  AND strftime('%Y-%m', date)=?
            """, (worker_id, month)).fetchone()[0]

            # Count approved leaves
            approved_leaves = conn.execute("""
                SELECT COUNT(*) 
                FROM leaves 
                WHERE worker_id=?
                  AND status='Approved'
                  AND strftime('%Y-%m', start_date)=?
            """, (worker_id, month)).fetchone()[0]

            payable_days = present_days + approved_leaves
            daily_salary = monthly_salary / 30
            total_salary = round(payable_days * daily_salary, 2)

            result = {
                "present_days": present_days,
                "approved_leaves": approved_leaves,
                "payable_days": payable_days,
                "total_salary": total_salary
            }

    conn.close()
    return render_template(
        "admin_salary_calculation.html",
        workers=workers,
        result=result
    )

# ---------------- SALARY PAYMENT ----------------
@app.route("/admin/hrms/salary-payment", methods=["GET", "POST"])
@login_required
def salary_payment():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    conn = get_db()
    workers = conn.execute("SELECT id, username FROM workers").fetchall()
    result = None
    already_paid = False

    if request.method == "POST":
        worker_id = request.form["worker_id"]
        month = request.form["month"]

        # Check duplicate payment
        paid = conn.execute("""
            SELECT * FROM salary_payments
            WHERE worker_id=? AND month=?
        """, (worker_id, month)).fetchone()

        if paid:
            already_paid = True
        else:
            # Attendance
            present = conn.execute("""
                SELECT COUNT(*) FROM attendance
                WHERE worker_id=? AND status='Present'
                AND strftime('%Y-%m', date)=?
            """, (worker_id, month)).fetchone()[0]

            leaves = conn.execute("""
                SELECT COUNT(*) FROM leaves
                WHERE worker_id=? AND status='Approved'
                AND strftime('%Y-%m', start_date)=?
            """, (worker_id, month)).fetchone()[0]

            payable = present + leaves

            salary = conn.execute("""
                SELECT * FROM salary_settings WHERE worker_id=?
            """, (worker_id,)).fetchone()

            if salary:
                if salary["salary_type"] == "daily":
                    total = payable * salary["amount"]
                else:
                    per_day = salary["amount"] / salary["working_days"]
                    total = round(payable * per_day, 2)

                result = {
                    "worker_id": worker_id,
                    "month": month,
                    "total": total
                }

    conn.close()
    return render_template(
        "admin_salary_payment.html",
        workers=workers,
        result=result,
        already_paid=already_paid
    )


@app.route("/admin/hrms/salary-payment/confirm", methods=["POST"])
@login_required
def confirm_salary_payment():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    worker_id = request.form["worker_id"]
    month = request.form["month"]
    amount = request.form["amount"]
    remarks = request.form.get("remarks")

    conn = get_db()
    conn.execute("""
        INSERT INTO salary_payments
        (worker_id, month, amount, remarks)
        VALUES (?, ?, ?, ?)
    """, (worker_id, month, amount, remarks))

    conn.commit()
    conn.close()

    return redirect(url_for("salary_payment"))

# ---------------- SALARY REPORT ----------------
@app.route("/admin/hrms/salary-reports")
@login_required
def salary_reports():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    conn = get_db()
    reports = conn.execute("""
        SELECT 
            sp.month,
            sp.amount,
            sp.paid_on,
            sp.remarks,
            w.username
        FROM salary_payments sp
        JOIN workers w ON w.id = sp.worker_id
        ORDER BY sp.paid_on DESC
    """).fetchall()
    conn.close()

    return render_template("admin_salary_reports.html", reports=reports)




@app.route("/admin/hrms/reports")
@login_required
def admin_hrms_reports():
    return "HRMS Reports – Coming Soon"


# ---------------- ADMIN REPORTS ----------------
@app.route("/admin/reports/download")
@login_required
def download_reports():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    conn = get_db()

    # Web Leads
    leads = pd.read_sql_query(
        "SELECT name, mobile, email, service, status, created_at FROM web_leads",
        conn
    )

    # Appointments
    appointments = pd.read_sql_query(
        "SELECT name, mobile, service, status, payment, created_at FROM appointments",
        conn
    )

    conn.close()

    # Create Excel
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")

    with pd.ExcelWriter(temp_file.name, engine="openpyxl") as writer:
        leads.to_excel(writer, sheet_name="Web Leads", index=False)
        appointments.to_excel(writer, sheet_name="Appointments", index=False)

    return send_file(
        temp_file.name,
        as_attachment=True,
        download_name="niva_reports.xlsx"
    )
@app.route('/admin/joining-letter', methods=['GET', 'POST'])
def admin_joining_letter():
    if request.method == 'POST':
        employee_name = request.form['employee_name']
        designation = request.form['designation']
        department = request.form['department']
        joining_date = request.form['joining_date']
        salary = request.form['salary']
        employment_type = request.form['employment_type']
        work_location = request.form['work_location']

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO joining_letters (
                employee_name,
                designation,
                department,
                joining_date,
                salary,
                employment_type,
                work_location
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            employee_name,
            designation,
            department,
            joining_date,
            salary,
            employment_type,
            work_location
        ))

        letter_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # 🔹 Generate PDF immediately
        data = {
            "employee_name": employee_name,
            "designation": designation,
            "department": department,
            "joining_date": joining_date,
            "salary": salary,
            "employment_type": employment_type,
            "work_location": work_location
        }

        pdf_path = f"joining_letter_{letter_id}.pdf"
        generate_joining_letter_pdf(data, pdf_path)

        return send_file(pdf_path, as_attachment=True)

    return render_template('admin_joining_letter.html')

@app.route('/admin/joining-letters')
def admin_joining_letters_list():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM joining_letters
        ORDER BY created_at DESC
    """)
    letters = cursor.fetchall()

    conn.close()

    return render_template(
        'admin_joining_letters_list.html',
        letters=letters
    )
@app.route('/admin/joining-letter/pdf/<int:letter_id>')
def generate_joining_letter(letter_id):
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    letter = cursor.execute(
        "SELECT * FROM joining_letters WHERE id = ?",
        (letter_id,)
    ).fetchone()

    conn.close()

    if not letter:
        return "Joining letter not found", 404

    data = {
        "employee_name": letter["employee_name"],
        "designation": letter["designation"],
        "department": letter["department"],
        "joining_date": letter["joining_date"],
        "salary": letter["salary"],
        "employment_type": letter["employment_type"],
        "work_location": letter["work_location"]
    }

    pdf_path = f"joining_letter_{letter_id}.pdf"
    generate_joining_letter_pdf(data, pdf_path)

    return send_file(pdf_path, as_attachment=True)


# ---------------- ADMIN HR MESSAGES ----------------
@app.route("/admin/hrms/messages", methods=["GET", "POST"])
@login_required
def admin_hr_messages():
    if current_user.role != "admin":
        return redirect(url_for("login"))

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Handle reply
    if request.method == "POST":
        msg_id = request.form.get("msg_id")
        reply = request.form.get("reply")

        cursor.execute("""
            UPDATE hr_messages
            SET reply = ?, status = 'Replied'
            WHERE id = ?
        """, (reply, msg_id))

        conn.commit()

    # Fetch all messages
    cursor.execute("""
        SELECT 
            m.*,
            w.username
        FROM hr_messages m
        JOIN workers w ON w.id = m.worker_id
        ORDER BY m.created_at DESC
    """)

    messages = cursor.fetchall()
    conn.close()

    return render_template(
        "admin_hr_messages.html",
        messages=messages
    )


# ---------------- LOGOUT ----------------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))




@app.route("/api/web-leads", methods=["POST"])
def create_web_lead():
    try:
        data = request.get_json(force=True)
        print("DATA RECEIVED:", data)

        name = data.get("name")
        mobile_no = data.get("mobile_no")
        email = data.get("email", "")
        service = data.get("service")
        message = data.get("message", "")
        location = data.get("location", "")

        if not name or not mobile_no or not service:
            return jsonify({"error": "Required fields missing"}), 400

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO web_leads
            (name, mobile, email, service, message, address, payment_type, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            mobile_no,
            email,
            service,
            message,
            location,
            "Pending",
            "New"
        ))

        conn.commit()
                # 🔔 Send Telegram Notification
        telegram_message = f"""
        🔥 <b>New Website Lead</b>

        👤 <b>Name:</b> {name}
        📞 <b>Mobile:</b> {mobile_no}
        📧 <b>Email:</b> {email}
        🛠 <b>Service:</b> {service}
        📍 <b>Location:</b> {location}
        📝 <b>Message:</b> {message}
        """

        send_telegram_notification(telegram_message)

        conn.close()

        return jsonify({
            "success": True,
            "message": "Booking received successfully"
        }), 201

    except Exception as e:
        print("BACKEND ERROR:", str(e))
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500




# Razorpay 
@app.route("/create-order", methods=["POST"])
def create_order():
    try:
        data = request.get_json()
        items = data.get("items", [])

        if not items or not isinstance(items, list):
            return jsonify({"error": "No items received"}), 400

        total_amount = 0

        for item in items:
            try:
                price = int(float(item.get("price", 0)))
            except:
                price = 0
            total_amount += price

        if total_amount <= 0:
            return jsonify({"error": "Invalid total amount"}), 400

        # Razorpay expects amount in paise
        order = client.order.create({
            "amount": total_amount * 100,
            "currency": "INR",
            "payment_capture": 1
        })

        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"]
        })

    except Exception as e:
        print("Create order error:", e)
        return jsonify({"error": "Order creation failed"}), 500

@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    try:
        data = request.get_json(force=True)

        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")
        lead_id = data.get("lead_id")  # 🔥 we add this

        if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature or not lead_id:
            return jsonify({"success": False, "error": "Missing payment details"}), 400

        params = {
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature
        }

        # ✅ Verify Razorpay signature
        client.utility.verify_payment_signature(params)

        # ✅ Update database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE web_leads
            SET payment_type = 'Paid',
                razorpay_payment_id = ?
            WHERE id = ?
        """, (razorpay_payment_id, lead_id))

        conn.commit()
        conn.close()

        return jsonify({"success": True})

    except razorpay.errors.SignatureVerificationError:
        return jsonify({"success": False, "error": "Signature verification failed"}), 400

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



# Run Flask app
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000, debug=True)

if __name__ == "__main__":
    app.run(debug=True)