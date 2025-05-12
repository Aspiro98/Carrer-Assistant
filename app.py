from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)
import fitz  # PyMuPDF
import docx
from openai import OpenAI
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.mime.text import MIMEText
import base64
from io import BytesIO
import json

app = Flask(__name__)
app.secret_key = "supersecretkey123"
import os
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# SQLite Database Setup
DATABASE = "users.db"


def init_db():
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            name TEXT,
            task_count INTEGER DEFAULT 0,
            profile_image TEXT,
            dashboard_config TEXT
        )"""
        )
        try:
            c.execute("ALTER TABLE users ADD COLUMN dashboard_config TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()


# Initialize the database
init_db()


# Email sending function
def send_confirmation_email(email, username):
    sender_email = "your_email@example.com"
    sender_password = "your_password"
    msg = MIMEText(
        f"Dear {username},\n\nYour account has been successfully created with Career Assistant!\n\nBest regards,\nCareer Assistant Team"
    )
    msg["Subject"] = "Account Creation Confirmation"
    msg["From"] = sender_email
    msg["To"] = email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, email, msg.as_string())
    except Exception as e:
        print(f"Failed to send email: {str(e)}")


# Extract Text
def extract_text(file):
    filename = file.filename.lower()
    if filename.endswith(".pdf"):
        doc = fitz.open(stream=file.read(), filetype="pdf")
        return "".join(page.get_text() for page in doc)
    elif filename.endswith(".docx"):
        doc = docx.Document(file)
        return "\n".join([p.text for p in doc.paragraphs])
    return ""


# Login required decorator
def login_required(f):
    def wrap(*args, **kwargs):
        if "user_id" not in session or not session.get("user_id"):
            flash("Please log in to access this page.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    wrap.__name__ = f.__name__
    return wrap


def increment_user_task_count(user_id):
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE users SET task_count = task_count + 1 WHERE id = ?", (user_id,)
        )
        conn.commit()


def get_user_task_count(user_id):
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute("SELECT task_count FROM users WHERE id = ?", (int(user_id),))
        result = c.fetchone()
        return result[0] if result else 0


def get_user_profile(user_id):
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT phone, profile_image, dashboard_config FROM users WHERE id = ?",
            (int(user_id),),
        )
        result = c.fetchone()
        return {
            "phone": result[0] if result[0] else "",
            "profile_image": result[1] if result[1] else "",
            "dashboard_config": (
                json.loads(result[2])
                if result[2]
                else {
                    "cards": [
                        "resume",
                        "interview",
                        "job_analyzer",
                        "linkedin",
                        "planner",
                    ],
                    "positions": {},
                    "sizes": {},
                }
            ),
        }


def save_dashboard_config(user_id, config):
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE users SET dashboard_config = ? WHERE id = ?",
            (json.dumps(config), user_id),
        )
        conn.commit()


# Mock data for tasks on dashboard with routes
def get_tasks():
    return [
        {
            "name": "Resume Analyzer",
            "description": "Upload your resume to get AI-powered suggestions for improvement.",
            "route": "resume",
        },
        {
            "name": "Interview Prep",
            "description": "Generate mock interview questions based on your job role.",
            "route": "interview",
        },
        {
            "name": "Job Analyzer",
            "description": "Compare your resume with a job description to identify gaps.",
            "route": "job_analyzer",
        },
        {
            "name": "LinkedIn Optimizer",
            "description": "Optimize your LinkedIn summary for better visibility.",
            "route": "linkedin",
        },
        {
            "name": "Career Planner",
            "description": "Create a personalized roadmap to achieve your career goals.",
            "route": "planner",
        },
    ]


# Routes
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        phone = request.form.get("phone")

        if not username or not email or not password or not confirm_password:
            flash("All fields are required.", "error")
            return redirect(url_for("register"))
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        try:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO users (username, email, password, phone, name, task_count) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        username,
                        email,
                        generate_password_hash(password),
                        phone,
                        username,
                        0,
                    ),
                )
                conn.commit()
            send_confirmation_email(email, username)
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username or email already exists.", "error")
            return redirect(url_for("register"))
    return render_template(
        "register.html", user_profile={"phone": "", "profile_image": ""}
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("identifier")
        password = request.form.get("password")

        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT * FROM users WHERE username = ? OR email = ?",
                (identifier, identifier),
            )
            user = c.fetchone()

        if user and check_password_hash(user[3], password):
            session.clear()
            session["user_id"] = user[0]
            session["username"] = user[1]
            session["name"] = user[5] or user[1]
            flash("Logged in successfully!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username/email or password.", "error")
        return redirect(url_for("login"))
    return render_template(
        "login.html", user_profile={"phone": "", "profile_image": ""}
    )


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_id = session["user_id"]
    user_profile = get_user_profile(user_id)

    if request.method == "POST":
        new_name = request.form.get("name")
        new_phone = request.form.get("phone")
        new_password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        profile_image = request.files.get("profile_image")

        if new_password and new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("profile"))
        password_hash = generate_password_hash(new_password) if new_password else None

        profile_image_data = user_profile["profile_image"]
        if profile_image and profile_image.filename:
            if not profile_image.filename.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif")
            ):
                flash("Invalid image format.", "error")
                return redirect(url_for("profile"))
            profile_image_data = base64.b64encode(profile_image.read()).decode("utf-8")

        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            if password_hash:
                c.execute(
                    "UPDATE users SET name = ?, phone = ?, password = ?, profile_image = ? WHERE id = ?",
                    (new_name, new_phone, password_hash, profile_image_data, user_id),
                )
            else:
                c.execute(
                    "UPDATE users SET name = ?, phone = ?, profile_image = ? WHERE id = ?",
                    (new_name, new_phone, profile_image_data, user_id),
                )
            conn.commit()

        session["name"] = new_name
        flash("Profile updated successfully!", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html", user_profile=user_profile)


@app.route("/", methods=["GET"])
def index():
    user_id = session.get("user_id")
    if user_id:
        return redirect(url_for("dashboard"))
    user_profile = {"phone": "", "profile_image": ""}
    return render_template("index.html", user_profile=user_profile)


@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    user_id = session.get("user_id")
    user_profile = (
        get_user_profile(user_id)
        if user_id
        else {
            "phone": "",
            "profile_image": "",
            "dashboard_config": {
                "cards": ["resume", "interview", "job_analyzer", "linkedin", "planner"],
                "positions": {},
                "sizes": {},
            },
        }
    )
    tasks = get_tasks()
    if request.method == "POST" and user_id:
        config = request.form.get("dashboard_config", "{}")
        save_dashboard_config(user_id, json.loads(config))
        flash("Dashboard updated!", "success")
        return redirect(url_for("dashboard"))
    return render_template("home.html", tasks=tasks, user_profile=user_profile)


@app.route("/resume", methods=["GET", "POST"])
@login_required
def resume():
    user_id = session["user_id"]
    user_profile = get_user_profile(user_id)
    gpt_response = None
    if request.method == "POST":
        file = request.files["resume"]
        if file:
            content = extract_text(file)
            prompt = f"Analyze this resume and suggest improvements:\n\n{content}"
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
            )
            gpt_response = response.choices[0].message.content
            increment_user_task_count(session["user_id"])
    return render_template(
        "resume.html", gpt_response=gpt_response, user_profile=user_profile
    )


@app.route("/interview", methods=["GET", "POST"])
@login_required
def interview():
    user_id = session["user_id"]
    user_profile = get_user_profile(user_id)
    questions = None
    if request.method == "POST":
        role = request.form.get("job_role")
        if role:
            prompt = f"Generate 5 mock interview questions for a {role} role."
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            questions = response.choices[0].message.content.split("\n")
            questions = [q.strip() for q in questions if q.strip()]
            increment_user_task_count(session["user_id"])
    return render_template(
        "interview.html", questions=questions, user_profile=user_profile
    )


@app.route("/get_feedback", methods=["POST"])
@login_required
def get_feedback():
    transcript = request.json.get("transcript", "")
    if not transcript:
        return jsonify({"error": "No transcript provided"}), 400

    prompt = f"Analyze the following interview transcript and provide feedback on clarity, confidence, and areas for improvement. The feedback should be structured as a numbered list. Each point should be clear, not too brief, and limited to 1 to 2 lines maximum. And each point and list should start in a new line rather than just continuing on the same line and also max it can generate points is limited to 3 points:\n\n{transcript}"
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )
    feedback = response.choices[0].message.content
    increment_user_task_count(session["user_id"])
    return jsonify({"feedback": feedback})


@app.route("/job_analyzer", methods=["GET", "POST"])
@login_required
def job_analyzer():
    user_id = session["user_id"]
    user_profile = get_user_profile(user_id)
    analysis = None
    if request.method == "POST":
        resume_file = request.files.get("resume")
        job_description = request.form.get("job_description")

        if resume_file and job_description:
            resume_text = extract_text(resume_file)
            prompt = (
                "Compare this resume:\n\n{resume}\n\nwith this job description:\n\n{jd}\n\n"
                "Provide a structured response with the following sections, each starting with the exact header:\n"
                "- Present skills: List all technical skills found in the resume. Structure them neatly as a numbered list. Each number and point must start on a new line (e.g., 1. Python 2. Java). Do not group multiple items on the same line."
                "- Present keywords: List other keywords present in the resume. Structure them neatly as a numbered list. Each number and point must start on a new line."
                "- Missing skills: List technical skills from the job description that are missing in the resume. Structure them neatly as a numbered list. Each number and point must start on a new line."
                "- Missing keywords: List other keywords from the job description that are missing in the resume. Structure them neatly as a numbered list. Each number and point must start on a new line."
                "- Improvement suggestions: Provide exactly 3 specific suggestions to better match the job description. Structure the suggestions as a numbered list. Each number and point must start on a new line. Each suggestion should be clear, not too brief, and limited to 1 to 2 lines maximum. Do not return more than 3 suggestions."

            ).format(resume=resume_text, jd=job_description)
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
            )
            analysis_text = response.choices[0].message.content
            print("Raw OpenAI Response:", analysis_text)  # Debug output
            analysis = {
                "present_skills": "",
                "present_keywords": "",
                "missing_skills": "",
                "missing_keywords": "",
                "suggestions": "",
            }
            current_section = None
            for line in analysis_text.split("\n"):
                line = line.strip()
                if line.startswith("- Present skills:"):
                    current_section = "present_skills"
                    analysis["present_skills"] = line.replace(
                        "- Present skills:", ""
                    ).strip()
                elif line.startswith("- Present keywords:"):
                    current_section = "present_keywords"
                    analysis["present_keywords"] = line.replace(
                        "- Present keywords:", ""
                    ).strip()
                elif line.startswith("- Missing skills:"):
                    current_section = "missing_skills"
                    analysis["missing_skills"] = line.replace(
                        "- Missing skills:", ""
                    ).strip()
                elif line.startswith("- Missing keywords:"):
                    current_section = "missing_keywords"
                    analysis["missing_keywords"] = line.replace(
                        "- Missing keywords:", ""
                    ).strip()
                elif line.startswith("- Improvement suggestions:"):
                    current_section = "suggestions"
                    analysis["suggestions"] = line.replace(
                        "- Improvement suggestions:", ""
                    ).strip()
                elif current_section and line and not line.startswith("-"):
                    analysis[current_section] += " " + line
            for key in analysis:
                analysis[key] = analysis[key].strip() or "None identified."
            increment_user_task_count(session["user_id"])
    return render_template(
        "job_analyzer.html", analysis=analysis, user_profile=user_profile
    )


@app.route("/linkedin", methods=["GET", "POST"])
@login_required
def linkedin():
    user_id = session["user_id"]
    user_profile = get_user_profile(user_id)
    optimized_summary = None
    if request.method == "POST":
        summary = request.form.get("linkedin_summary")
        if summary:
            prompt = (
                f"Improve this LinkedIn summary for clarity and impact:\n\n{summary}"
            )
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
            )
            optimized_summary = response.choices[0].message.content
            increment_user_task_count(session["user_id"])
    return render_template(
        "linkedin.html", optimized_summary=optimized_summary, user_profile=user_profile
    )


@app.route("/planner", methods=["GET", "POST"])
@login_required
def planner():
    user_id = session["user_id"]
    user_profile = get_user_profile(user_id)
    roadmap = None
    if request.method == "POST":
        goal = request.form.get("goal")
        if goal:
            prompt = f"Create a personalized career roadmap for the following goal:\n\n{goal}"
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
            )
            roadmap = response.choices[0].message.content
            increment_user_task_count(session["user_id"])
    return render_template("planner.html", roadmap=roadmap, user_profile=user_profile)


if __name__ == "__main__":
    app.run(debug=True)
