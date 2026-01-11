from flask import (
    Flask, render_template, request, redirect,
    session, jsonify, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

from storage import upload_file, list_files, get_download_url, delete_blob

import sqlite3
import os
import re
import io
import zipfile
import requests

# 👉 Email + token
import smtplib
from email.mime.text import MIMEText
from itsdangerous import URLSafeTimedSerializer
print("EMAIL:", os.getenv("EMAIL_ADDRESS"))
print("EMAIL PASS EXISTS:", bool(os.getenv("EMAIL_PASSWORD")))

# -----------------------------
# APP SETUP
# -----------------------------
app = Flask(__name__)
print("🚀 Flask app started")

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

serializer = URLSafeTimedSerializer(app.secret_key)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
)

@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response

# -----------------------------
# DATABASE
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "users.db")


def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# -----------------------------
# HELPERS
# -----------------------------
EMAIL_REGEX = r"[^@]+@[^@]+\.[^@]+"

def is_valid_email(email):
    return re.match(EMAIL_REGEX, email)

def require_login():
    return "user" in session

# -----------------------------
# AUTH
# -----------------------------
@app.route("/")
def root():
    return render_template("login.html")

@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()
    email = data.get("username")
    password = data.get("password")

    if not email or not password or not is_valid_email(email):
        return jsonify({"success": False})

    hashed = generate_password_hash(password)

    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("INSERT INTO users VALUES (?,?)", (email, hashed))
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        return jsonify({"success": False})

    session["user"] = email
    return jsonify({"success": True})

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("username")
    password = data.get("password")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    conn.close()

    if row and check_password_hash(row[0], password):
        session["user"] = email
        return jsonify({"success": True})

    return jsonify({"success": False})

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# -----------------------------
# DASHBOARD
# -----------------------------
@app.route("/dashboard")
def dashboard():
    if not require_login():
        return redirect("/")
    return render_template("index.html")

# -----------------------------
# UPLOAD
# -----------------------------
@app.route("/upload", methods=["POST"])
def upload():
    if not require_login():
        return jsonify({"error": "Unauthorized"}), 401

    file = request.files.get("file")
    path = request.form.get("path")

    if not file:
        return jsonify({"error": "No file"}), 400

    if path:
        path = path.replace("\\", "/").lstrip("/")

    upload_file(file, session["user"], path)
    return jsonify({"success": True})

# -----------------------------
# LIST FILES + FOLDERS
# -----------------------------
@app.route("/files")
def files():
    if not require_login():
        return redirect("/")

    user = session["user"]
    base = f"users/{user}/"

    path = request.args.get("path", "").strip("/")
    prefix = base + (path + "/" if path else "")

    folders = set()
    files = []

    for blob in list_files(user):
        name = blob.name
        if not name.startswith(prefix):
            continue

        relative = name[len(prefix):]
        if not relative:
            continue

        if "/" in relative:
            folders.add(relative.split("/")[0])
        else:
            if relative != ".keep":
                files.append(relative)

    return jsonify({
        "folders": sorted(folders),
        "files": sorted(files)
    })

# -----------------------------
# DOWNLOAD FILE
# -----------------------------
@app.route("/download")
def download_file():
    if not require_login():
        return jsonify({"error": "Unauthorized"}), 401

    blob = request.args.get("blob", "").strip("/")
    if not blob:
        return jsonify({"error": "Missing blob"}), 400

    blob_path = f"users/{session['user']}/{blob}"
    return jsonify({"url": get_download_url(blob_path)})

# -----------------------------
# DOWNLOAD FOLDER AS ZIP
# -----------------------------
@app.route("/download-folder")
def download_folder():
    if not require_login():
        return jsonify({"error": "Unauthorized"}), 401

    folder = request.args.get("path", "").strip("/")
    if not folder:
        return jsonify({"error": "Missing folder"}), 400

    user = session["user"]
    base = f"users/{user}/"
    prefix = f"{base}{folder}/"

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for blob in list_files(user):
            if blob.name.startswith(prefix) and not blob.name.endswith(".keep"):
                rel = blob.name[len(prefix):]
                zip_path = f"{folder}/{rel}"
                content = requests.get(get_download_url(blob.name)).content
                zipf.writestr(zip_path, content)

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{folder}.zip"
    )

# -----------------------------
# DELETE FILE
# -----------------------------
@app.route("/delete-file", methods=["POST"])
def delete_file():
    if not require_login():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    blob = data.get("blob", "").strip("/")

    if not blob:
        return jsonify({"error": "Missing file"}), 400

    blob_path = f"users/{session['user']}/{blob}"
    delete_blob(blob_path)

    return jsonify({"success": True})

# -----------------------------
# DELETE FOLDER
# -----------------------------
@app.route("/delete-folder", methods=["POST"])
def delete_folder():
    if not require_login():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    folder = data.get("path", "").strip("/")

    if not folder:
        return jsonify({"error": "Missing folder"}), 400

    user = session["user"]
    prefix = f"users/{user}/{folder}/"

    for blob in list_files(user):
        if blob.name.startswith(prefix):
            delete_blob(blob.name)

    return jsonify({"success": True})
# -----------------------------
# FORGOT PASSWORD - SEND EMAIL
# -----------------------------
@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"message": "Email required"}), 400

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT email FROM users WHERE email=?", (email,))
    user = cur.fetchone()
    conn.close()

    if not user:
        return jsonify({"message": "If this email exists, a reset link was sent."})

    token = serializer.dumps(email, salt="reset-password")
    reset_link = request.host_url + f"reset/{token}"

    msg = MIMEText(
        f"Click the link to reset your password:\n\n{reset_link}\n\n"
        "If you did not request this, ignore this email."
    )
    msg["Subject"] = "Reset Your FREEDRIVE Password"
    msg["From"] = os.getenv("EMAIL_ADDRESS")
    msg["To"] = email

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(os.getenv("EMAIL_ADDRESS"), os.getenv("EMAIL_PASSWORD"))
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print("Email error:", e)
        return jsonify({"message": "Failed to send email"}), 500

    return jsonify({"message": "Reset link sent to your email."})

# -----------------------------
# RESET PASSWORD PAGE
# -----------------------------
@app.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = serializer.loads(token, salt="reset-password", max_age=1800)
    except Exception:
        return "Invalid or expired link"

    if request.method == "POST":
        new_password = request.form.get("password")
        hashed = generate_password_hash(new_password)

        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("UPDATE users SET password=? WHERE email=?", (hashed, email))
        conn.commit()
        conn.close()

        return redirect("/")

    return render_template("reset_password.html")