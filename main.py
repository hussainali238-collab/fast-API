
from fastapi import FastAPI, Request, HTTPException, status, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import sqlite3
import json
import os
from contextlib import closing


# ----------------------------------
# 1. Project paths
# ----------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE = os.path.join(BASE_DIR, "students.db")
DATA_FILE = os.path.join(BASE_DIR, "students.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static"
)

templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ----------------------------------
# 2. Initial student data
# ----------------------------------

INITIAL_STUDENTS = [
    {
        "id": 1,
        "name": "Ali Khan",
        "age": 20,
        "city": "Lahore",
        "email": "ali@example.com",
        "course": "Computer Science",
        "bio": "Ali is interested in web development and Python."
    },
    {
        "id": 2,
        "name": "Ahmed Raza",
        "age": 21,
        "city": "Karachi",
        "email": "ahmed@example.com",
        "course": "Software Engineering",
        "bio": "Ahmed enjoys programming and learning new technologies."
    },
    {
        "id": 3,
        "name": "Usman Malik",
        "age": 19,
        "city": "Islamabad",
        "email": "usman@example.com",
        "course": "Computer Science",
        "bio": "Usman likes solving programming problems."
    },
    {
        "id": 4,
        "name": "Hamza Shah",
        "age": 22,
        "city": "Multan",
        "email": "hamza@example.com",
        "course": "Information Technology",
        "bio": "Hamza is interested in databases and backend development."
    },
    {
        "id": 5,
        "name": "Bilal Ahmed",
        "age": 20,
        "city": "Faisalabad",
        "email": "bilal@example.com",
        "course": "Computer Science",
        "bio": "Bilal enjoys building small web applications."
    },
    {
        "id": 6,
        "name": "Hassan Ali",
        "age": 21,
        "city": "Rawalpindi",
        "email": "hassan@example.com",
        "course": "Software Engineering",
        "bio": "Hassan likes learning about APIs and backend systems."
    },
    {
        "id": 7,
        "name": "Saad Ahmed",
        "age": 19,
        "city": "Lahore",
        "email": "saad@example.com",
        "course": "Information Technology",
        "bio": "Saad is passionate about technology and computers."
    },
    {
        "id": 8,
        "name": "Usama Khan",
        "age": 23,
        "city": "Peshawar",
        "email": "usama@example.com",
        "course": "Computer Science",
        "bio": "Usama enjoys Python programming and automation."
    },
    {
        "id": 9,
        "name": "Ayesha Noor",
        "age": 20,
        "city": "Lahore",
        "email": "ayesha@example.com",
        "course": "Software Engineering",
        "bio": "Ayesha is interested in frontend and UI design."
    }
]


def create_table():
    with closing(sqlite3.connect(DATABASE)) as conn:
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
            count = conn.execute(
                "SELECT COUNT(*) FROM students"
            ).fetchone()[0]
            if count == 0:
                # Import existing JSON records if available
                if os.path.exists(DATA_FILE):
                    try:
                        with open(
                            DATA_FILE, "r", encoding="utf-8"
                        ) as file:
                            saved_students = json.load(file)
                        if not isinstance(saved_students, list):
                            saved_students = []
                    except (json.JSONDecodeError, OSError):
                        saved_students = []
                else:
                    saved_students = []
                # Use initial records if JSON has no records
                if not saved_students:
                    saved_students = INITIAL_STUDENTS
                for student in saved_students:
                    conn.execute("""
                        INSERT INTO students
                            (id, name, age, city, email, course, bio)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        student["id"],
                        student["name"],
                        student["age"],
                        student["city"],
                        student["email"],
                        student["course"],
                            student["bio"]
                        ))


create_table()


@app.get("/")
def home(request: Request):

    with closing(sqlite3.connect(DATABASE)) as conn:
        conn.row_factory = sqlite3.Row

        students = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM students ORDER BY id"
            ).fetchall()
        ]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "students": students
        }
    )


@app.get("/student/{student_id}")
def student_details(request: Request, student_id: int):

    with closing(sqlite3.connect(DATABASE)) as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT * FROM students WHERE id = ?",
            (student_id,)
        ).fetchone()

        student = dict(row) if row else None

    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )

    return templates.TemplateResponse(
        request=request,
        name="student.html",
        context={
            "request": request,
            "student": student
        }
    )

@app.get("/add-student")
def add_student_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="add_student.html",
        context={"request": request}
    )



@app.post("/students")
def create_student(
    name: str = Form(...),
    age: int = Form(...),
    city: str = Form(...),
    email: str = Form(...),
    course: str = Form(...),
    bio: str = Form(...)
):

    with closing(sqlite3.connect(DATABASE)) as conn:
        with conn:
            cursor = conn.execute("""
                INSERT INTO students
                    (name, age, city, email, course, bio)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                name,
                age,
                city,
                email,
                course,
                bio
            ))

            new_id = cursor.lastrowid

    return RedirectResponse(
        url=f"/student/{new_id}",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/search-student")
def search_student_page(request: Request, q: str = ""):

    students = []

    if q.strip():
        search_term = q.strip()

        with sqlite3.connect(DATABASE) as conn:
            conn.row_factory = sqlite3.Row

            if search_term.isdigit():
                rows = conn.execute("""
                    SELECT * FROM students
                    WHERE id = ? OR name LIKE ?
                    ORDER BY id
                """, (int(search_term), f"%{search_term}%")).fetchall()

            else:
                # Search by student name
                rows = conn.execute("""
                    SELECT * FROM students
                    WHERE name LIKE ?
                    ORDER BY id
                """, (f"%{search_term}%",)).fetchall()

            students = [dict(row) for row in rows]

    return templates.TemplateResponse(
        request=request,
        name="search_student.html",
        context={
            "request": request,
            "q": q,
            "students": students
        }
    )


# ----------------------------------
# Edit Student
# ----------------------------------

@app.get("/edit-student/{student_id}")
def edit_student_page(request: Request, student_id: int):

    with closing(sqlite3.connect(DATABASE)) as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT * FROM students WHERE id = ?",
            (student_id,)
        ).fetchone()

        student = dict(row) if row else None

    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )

    return templates.TemplateResponse(
        request=request,
        name="edit_student.html",
        context={
            "request": request,
            "student": student
        }
    )


# ----------------------------------
# Update Student
# ----------------------------------

@app.post("/update-student/{student_id}")
def update_student(
    student_id: int,
    name: str = Form(...),
    age: int = Form(...),
    city: str = Form(...),
    email: str = Form(...),
    course: str = Form(...),
    bio: str = Form(...)
):

    with closing(sqlite3.connect(DATABASE)) as conn:
        with conn:
            cursor = conn.execute("""
                UPDATE students
                SET name = ?,
                    age = ?,
                    city = ?,
                    email = ?,
                    course = ?,
                    bio = ?
                WHERE id = ?
            """, (
                name,
                age,
                city,
                email,
                course,
                bio,
                student_id
            ))

            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Student not found"
                )

    return RedirectResponse(
        url=f"/student/{student_id}",
        status_code=status.HTTP_303_SEE_OTHER
    )