import os
import sqlite3
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv

from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pwdlib import PasswordHash
from starlette.middleware.sessions import SessionMiddleware

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "students.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="Student Management Portal")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "CHANGE-THIS-SECRET-BEFORE-DEPLOYMENT"),
    session_cookie="student_portal_session",
    max_age=60 * 60 * 8,
    same_site="lax",
    https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
password_hash = PasswordHash.recommended()


def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_table():
    with closing(get_connection()) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    age INTEGER NOT NULL,
                    city TEXT NOT NULL,
                    email TEXT NOT NULL,
                    course TEXT NOT NULL,
                    bio TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'student')),
                    student_id INTEGER UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE SET NULL
                )
            """)
            # Create the first admin from environment variables. Never allow
            # public registration to choose or create the admin role.
            admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
            admin_password = os.getenv("ADMIN_PASSWORD", "")
            if admin_email and admin_password:
                existing = conn.execute(
                    "SELECT id FROM users WHERE email = ?", (admin_email,)
                ).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT INTO users (email, password_hash, role) VALUES (?, ?, 'admin')",
                        (admin_email, password_hash.hash(admin_password)),
                    )


create_table()


def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT id, email, role, student_id FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def require_login(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in.")
    return user


def require_admin(request: Request):
    user = require_login(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


def render(request: Request, template: str, context: dict):
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={"request": request, **context},
    )


def redirect(url: str):
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/")
def home(request: Request):
    user = get_current_user(request)
    if not user:
        return redirect("/login")
    return redirect("/admin" if user["role"] == "admin" else "/my-profile")


@app.get("/register")
def register_page(request: Request):
    if get_current_user(request):
        return redirect("/")
    return render(request, "register.html", {"error": None})


@app.post("/register")
def register(
    request: Request,
    name: str = Form(...),
    age: int = Form(...),
    city: str = Form(...),
    email: str = Form(...),
    course: str = Form(...),
    bio: str = Form(""),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    if get_current_user(request):
        return redirect("/")
    email = email.strip().lower()
    if age < 1 or age > 120:
        return render(request, "register.html", {"error": "Enter a valid age."})
    if len(password) < 8:
        return render(request, "register.html", {"error": "Password must be at least 8 characters."})
    if password != confirm_password:
        return render(request, "register.html", {"error": "Passwords do not match."})

    try:
        with closing(get_connection()) as conn:
            with conn:
                if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                    return render(request, "register.html", {"error": "An account with this email already exists."})
                cursor = conn.execute(
                    """INSERT INTO students (name, age, city, email, course, bio)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (name.strip(), age, city.strip(), email, course.strip(), bio.strip()),
                )
                student_id = cursor.lastrowid
                user_cursor = conn.execute(
                    """INSERT INTO users (email, password_hash, role, student_id)
                       VALUES (?, ?, 'student', ?)""",
                    (email, password_hash.hash(password), student_id),
                )
                user_id = user_cursor.lastrowid
        request.session.clear()
        request.session["user_id"] = user_id
        return redirect("/my-profile")
    except sqlite3.IntegrityError:
        return render(request, "register.html", {"error": "Could not create this account. Check whether the email is already registered."})


@app.get("/login")
def login_page(request: Request):
    if get_current_user(request):
        return redirect("/")
    return render(request, "login.html", {"error": None})


@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    email = email.strip().lower()
    with closing(get_connection()) as conn:
        user = conn.execute(
            "SELECT id, email, password_hash, role FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if not user or not password_hash.verify(password, user["password_hash"]):
        return render(request, "login.html", {"error": "Incorrect email or password."})

    request.session.clear()
    request.session["user_id"] = user["id"]
    return redirect("/admin" if user["role"] == "admin" else "/my-profile")


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")


@app.get("/admin")
def admin_dashboard(request: Request):
    admin = require_admin(request)
    with closing(get_connection()) as conn:
        students = [dict(row) for row in conn.execute(
            "SELECT * FROM students ORDER BY id DESC"
        ).fetchall()]
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return render(request, "index.html", {
        "students": students, "admin": admin, "total_users": total_users
    })


@app.get("/my-profile")
def my_profile(request: Request):
    user = require_login(request)
    if user["role"] == "admin":
        return redirect("/admin")
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE id = ?", (user["student_id"],)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    return render(request, "student.html", {"student": dict(row), "user": user})


@app.get("/my-profile/edit")
def edit_my_profile_page(request: Request):
    user = require_login(request)
    if user["role"] != "student":
        return redirect("/admin")
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE id = ?", (user["student_id"],)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    return render(request, "edit_student.html", {
        "student": dict(row), "form_action": "/my-profile/edit"
    })


@app.post("/my-profile/edit")
def edit_my_profile(
    request: Request,
    name: str = Form(...),
    age: int = Form(...),
    city: str = Form(...),
    email: str = Form(...),
    course: str = Form(...),
    bio: str = Form(""),
):
    user = require_login(request)
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Student access required.")
    if age < 1 or age > 120:
        raise HTTPException(status_code=400, detail="Enter a valid age.")
    email = email.strip().lower()
    try:
        with closing(get_connection()) as conn:
            with conn:
                conn.execute(
                    """UPDATE students SET name=?, age=?, city=?, email=?, course=?, bio=?
                       WHERE id=?""",
                    (name.strip(), age, city.strip(), email, course.strip(), bio.strip(), user["student_id"]),
                )
                conn.execute(
                    "UPDATE users SET email=? WHERE id=?",
                    (email, user["id"]),
                )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="That email address is already in use.")
    return redirect("/my-profile")


@app.get("/student/{student_id}")
def student_details(request: Request, student_id: int):
    user = require_login(request)
    if user["role"] == "student" and user["student_id"] != student_id:
        raise HTTPException(status_code=403, detail="You can only view your own profile.")
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Student not found.")
    return render(request, "student.html", {"student": dict(row), "user": user})


@app.get("/add-student")
def add_student_page(request: Request):
    require_admin(request)
    return render(request, "add_student.html", {})


@app.post("/students")
def create_student(
    request: Request,
    name: str = Form(...),
    age: int = Form(...),
    city: str = Form(...),
    email: str = Form(...),
    course: str = Form(...),
    bio: str = Form(""),
):
    require_admin(request)
    if age < 1 or age > 120:
        raise HTTPException(status_code=400, detail="Enter a valid age.")
    with closing(get_connection()) as conn:
        with conn:
            cursor = conn.execute(
                """INSERT INTO students (name, age, city, email, course, bio)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name.strip(), age, city.strip(), email.strip().lower(), course.strip(), bio.strip()),
            )
            new_id = cursor.lastrowid
    return redirect(f"/student/{new_id}")


@app.get("/search-student")
def search_student_page(request: Request, q: str = ""):
    require_admin(request)
    students = []
    if q.strip():
        term = q.strip()
        with closing(get_connection()) as conn:
            if term.isdigit():
                rows = conn.execute(
                    "SELECT * FROM students WHERE id=? OR name LIKE ? ORDER BY id",
                    (int(term), f"%{term}%"),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM students WHERE name LIKE ? ORDER BY id",
                    (f"%{term}%",),
                ).fetchall()
            students = [dict(row) for row in rows]
    return render(request, "search_student.html", {"q": q, "students": students})


@app.get("/search-student-by-course")
def search_student_by_course(request: Request, course: str = ""):
    require_admin(request)
    with closing(get_connection()) as conn:
        if course:
            rows = conn.execute(
                "SELECT * FROM students WHERE course=? ORDER BY id", (course,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM students ORDER BY id").fetchall()
    return render(request, "index.html", {
        "request": request, "students": [dict(row) for row in rows],
        "admin": get_current_user(request), "total_users": 0
    })


@app.get("/edit-student/{student_id}")
def edit_student_page(request: Request, student_id: int):
    require_admin(request)
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Student not found.")
    return render(request, "edit_student.html", {
        "student": dict(row), "form_action": f"/update-student/{student_id}"
    })


@app.post("/update-student/{student_id}")
def update_student(
    request: Request,
    student_id: int,
    name: str = Form(...),
    age: int = Form(...),
    city: str = Form(...),
    email: str = Form(...),
    course: str = Form(...),
    bio: str = Form(""),
):
    require_admin(request)
    with closing(get_connection()) as conn:
        with conn:
            cursor = conn.execute(
                """UPDATE students SET name=?, age=?, city=?, email=?, course=?, bio=?
                   WHERE id=?""",
                (name.strip(), age, city.strip(), email.strip().lower(), course.strip(), bio.strip(), student_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Student not found.")
    return redirect(f"/student/{student_id}")


@app.post("/delete-student/{student_id}")
def delete_student(request: Request, student_id: int):
    require_admin(request)
    with closing(get_connection()) as conn:
        with conn:
            conn.execute("DELETE FROM students WHERE id=?", (student_id,))
    return redirect("/admin")
