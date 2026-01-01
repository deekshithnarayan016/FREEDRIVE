from flask import Flask, render_template, request, redirect, session, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from storage import upload_file, list_files, get_download_url
import sqlite3
import os
import re
import io
import zipfile

# -----------------------------
# APP SETUP
# -----------------------------
app = Flask(__name__)
print("🚀 Flask app started successfully")

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

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

# -----------------------------
# AUTH
# -----------------------------
@app.route("/")
def login_page():
    if "user" in session:
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
        return jsonify({"success": False, "error": "Email exists"})

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
    if "user" not in session:
        return redirect("/")
    return render_template("index.html", user=session["user"])

# -----------------------------
# UPLOAD
# -----------------------------
@app.route("/upload", methods=["POST"])
def upload():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    file = request.files.get("file")
    path = request.form.get("path")

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
    base = f"users/{session['user']}/"

    items = []
    seen_folders = set()

    for b in blobs:
        name = b.name.replace(base, "")
        if name.endswith(".keep"):
            continue

        if "/" in name:
            folder = name.split("/")[0]
            seen_folders.add(folder)
        else:
            items.append(name)

    for folder in seen_folders:
        items.append(folder + "/")

    return jsonify(sorted(items))

# -----------------------------
# DOWNLOAD FILE OR FOLDER
# -----------------------------
@app.route("/download")
def download():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    name = request.args.get("blob")
    if not name:
        return jsonify({"error": "Missing name"}), 400

    user = session["user"]
    base_path = f"users/{user}/"

    # -------- FILE DOWNLOAD --------
    if not name.endswith("/"):
        blob_path = base_path + name
        return jsonify({"url": get_download_url(blob_path)})

    # -------- FOLDER → ZIP DOWNLOAD --------
    folder_prefix = base_path + name

    blobs = list_files(user)
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for blob in blobs:
            if blob.name.startswith(folder_prefix) and not blob.name.endswith(".keep"):
                relative_path = blob.name.replace(base_path, "")
                file_url = get_download_url(blob.name)

                # Download blob content
                import requests
                content = requests.get(file_url).content
                zipf.writestr(relative_path, content)

    zip_buffer.seek(0)

    zip_name = name.rstrip("/") + ".zip"
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=zip_name
    )
