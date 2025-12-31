from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from storage import upload_file, list_files, get_download_url
import sqlite3
import os
import re

# -----------------------------
# APP SETUP
# -----------------------------
app = Flask(__name__)
print("🚀 Flask app started successfully")

# Azure reverse proxy fix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Secret key from Azure App Settings
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

# Secure session cookies (Azure HTTPS)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
)

# -----------------------------
# DATABASE SETUP
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

def is_valid_email(email: str) -> bool:
    return re.match(EMAIL_REGEX, email) is not None

# -----------------------------
# LOGIN PAGE
# -----------------------------
@app.route("/")
def login_page():
    if "user" in session:
        return redirect("/dashboard")
    return render_template("login.html")

# -----------------------------
# SIGNUP
# -----------------------------
@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()
    email = data.get("username")
    password = data.get("password")

    if not email or not password:
        return jsonify({"success": False, "error": "Missing fields"})

    if not is_valid_email(email):
        return jsonify({"success": False, "error": "Invalid email format"})

    hashed_pw = generate_password_hash(password)

    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("INSERT INTO users VALUES (?, ?)", (email, hashed_pw))
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "Email already registered"})

    session["user"] = email
    return jsonify({"success": True})

# -----------------------------
# LOGIN
# -----------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("username")
    password = data.get("password")

    if not email or not password:
        return jsonify({"success": False, "error": "Missing fields"})

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    conn.close()

    if row and check_password_hash(row[0], password):
        session["user"] = email
        return jsonify({"success": True})

    return jsonify({"success": False, "error": "Invalid credentials"})

# -----------------------------
# FORGOT PASSWORD (SAFE STUB)
# -----------------------------
@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    """
    SECURITY NOTE:
    - Never reveal if email exists
    - Always return same response
    """
    data = request.get_json()
    email = data.get("email")

    # TODO:
    # 1. Check if email exists
    # 2. Generate secure token
    # 3. Send reset email (SendGrid / SMTP)

    return jsonify({
        "message": "If this email exists, a password reset link was sent."
    })

# -----------------------------
# DASHBOARD
# -----------------------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return render_template("index.html", user=session["user"])

# -----------------------------
# LOGOUT
# -----------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# -----------------------------
# UPLOAD (FILES + FOLDERS)
# -----------------------------
@app.route("/upload", methods=["POST"])
def upload():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    file = request.files.get("file")
    path = request.form.get("path")  # 👈 NEW

    if not file:
        return jsonify({"error": "No file"}), 400

    upload_file(file, session["user"], path)
    return jsonify({"success": True})


# -----------------------------
# FILE LIST
# -----------------------------
@app.route("/files")
def files():
    if "user" not in session:
        return jsonify([])

    blobs = list_files(session["user"])
    return jsonify([
        b.name.replace(f"users/{session['user']}/", "")
        for b in blobs
    ])

# -----------------------------
# DOWNLOAD
# -----------------------------
@app.route("/download")
def download():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    filename = request.args.get("blob")
    if not filename:
        return jsonify({"error": "Missing filename"}), 400

    blob_path = f"users/{session['user']}/{filename}"
    return jsonify({"url": get_download_url(blob_path)})
