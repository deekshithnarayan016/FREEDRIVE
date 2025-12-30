from flask import Flask, render_template, request, redirect, session, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from storage import upload_file, list_files, get_download_url
import sqlite3
import os

# -----------------------------
# APP SETUP
# -----------------------------
app = Flask(__name__)
CORS(app)

# ✅ Secret key from environment (Azure-safe)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

# ✅ Session config (important for Azure HTTPS)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
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
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

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
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"success": False, "error": "Missing fields"})

    hashed_pw = generate_password_hash(password)

    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("INSERT INTO users VALUES (?, ?)", (username, hashed_pw))
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "User already exists"})

    session["user"] = username
    return jsonify({"success": True})

# -----------------------------
# LOGIN
# -----------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()

    if row and check_password_hash(row[0], password):
        session["user"] = username
        return jsonify({"success": True})

    return jsonify({"success": False, "error": "Invalid credentials"})

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
# UPLOAD
# -----------------------------
@app.route("/upload", methods=["POST"])
def upload():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file"}), 400

    upload_file(file, session["user"])
    return jsonify({"success": True})

# -----------------------------
# FILE LIST
# -----------------------------
@app.route("/files")
def files():
    if "user" not in session:
        return jsonify([])

    blobs = list_files(session["user"])
    return jsonify([b.name.split("/")[-1] for b in blobs])

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
