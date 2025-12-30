from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from storage import upload_file, list_files, get_download_url
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "pdrive-secret-key"

DB = "users.db"

# -----------------------------
# DB INIT
# -----------------------------
if not os.path.exists(DB):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE users (username TEXT PRIMARY KEY, password TEXT)"
    )
    conn.commit()
    conn.close()

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
    username = data["username"]
    password = generate_password_hash(data["password"])

    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("INSERT INTO users VALUES (?,?)", (username, password))
        conn.commit()
        conn.close()
    except:
        return jsonify({"success": False, "error": "User exists"})

    session["user"] = username
    return jsonify({"success": True})

# -----------------------------
# LOGIN
# -----------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data["username"]
    password = data["password"]

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()

    if row and check_password_hash(row[0], password):
        session["user"] = username
        return jsonify({"success": True})

    return jsonify({"success": False})

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
    upload_file(file, session["user"])
    return jsonify({"ok": True})

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
    blob = f"users/{session['user']}/{filename}"
    return jsonify({"url": get_download_url(blob)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
