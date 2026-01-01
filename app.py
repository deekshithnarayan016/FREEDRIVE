from flask import (
    Flask, render_template, request, redirect,
    session, jsonify, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

from storage import (
    upload_file,
    list_files,
    get_download_url
)

import sqlite3
import os
import re
import io
import zipfile
import requests

# -----------------------------
# APP SETUP
# -----------------------------
app = Flask(__name__)
print("🚀 Flask app started")

# Azure reverse proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Secret key
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

# Secure cookies (Azure HTTPS)
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
def login_page():
    if require_login():
        return redirect("/dashboard")
    return render_template("login.html")

@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()
    email = data.get("username")
    password = data.get("password")

    if not email or not password or not is_valid_email(email):
        return jsonify({"success": False, "error": "Invalid data"})

    hashed = generate_password_hash(password)

    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("INSERT INTO users VALUES (?,?)", (email, hashed))
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "Email already exists"})

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

    return jsonify({"success": False, "error": "Invalid credentials"})

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
    return render_template("index.html", user=session["user"])

# -----------------------------
# UPLOAD (FILES + FOLDERS)
# -----------------------------
@app.route("/upload", methods=["POST"])
def upload():
    if not require_login():
        return jsonify({"error": "Unauthorized"}), 401

    file = request.files.get("file")
    path = request.form.get("path")

    if not file:
        return jsonify({"error": "No file"}), 400

    upload_file(file, session["user"], path)
    return jsonify({"success": True})

# -----------------------------
# LIST FILES + FOLDERS (CRITICAL)
# -----------------------------
@app.route("/files")
def files():
    if not require_login():
        return jsonify({"files": [], "folders": []})

    user = session["user"]
    base = f"users/{user}/"

    path = request.args.get("path", "").strip("/")
    prefix = base + (path + "/" if path else "")

    files = []
    folders = set()

    for blob in list_files(user):
        if not blob.name.startswith(prefix):
            continue

        rel = blob.name.replace(prefix, "", 1)

        if not rel or rel.endswith(".keep"):
            continue

        if "/" in rel:
            folders.add(rel.split("/")[0])
        else:
            files.append(rel)

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

    blob = request.args.get("blob")
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
                rel_path = blob.name.replace(base, "", 1)
                url = get_download_url(blob.name)
                content = requests.get(url).content
                zipf.writestr(rel_path, content)

    zip_buffer.seek(0)

    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{folder}.zip"
    )
