# Free Hosting & Deployment Guide
## GES PLC Digital Attendance System

This guide outlines step-by-step processes to host and deploy the Flask PLC Attendance System online for **100% free**.

---

## Pre-Deployment Overview

Your application already includes the necessary production files:
- **`Procfile`**: Pre-configured with Gunicorn (`web: gunicorn wsgi:app`).
- **`wsgi.py`**: Production WSGI entry point (`application = create_app()`).
- **`requirements.txt`**: Includes `Flask`, `Flask-SQLAlchemy`, `Flask-Login`, `Flask-WTF`, `email-validator`, and `gunicorn`.
- **`seed.py`**: Automated database setup and initial admin/teacher credentials.

---

## Option 1: Render.com (Recommended)

[Render](https://render.com) offers a free cloud web service tier with automatic SSL (`https://`), continuous deployment from GitHub, and seamless support for Python WSGI applications.

### Step 1: Push Project to GitHub

1. Open your terminal in the `plc-attendance` directory:
   ```bash
   cd plc-attendance
   ```
2. Initialize Git and commit all project files:
   ```bash
   git init
   git add .
   git commit -m "Initial commit for production deployment"
   ```
3. Create a new repository on [GitHub](https://github.com/new) (e.g. `plc-attendance-system`).
4. Link and push your local code:
   ```bash
   git remote add origin https://github.com/<your-github-username>/plc-attendance-system.git
   git branch -M main
   git push -u origin main
   ```

---

### Step 2: Create Web Service on Render

1. Log in to [Render](https://render.com) using your GitHub account.
2. Click **"New +"** in the top navigation bar and select **"Web Service"**.
3. Select **"Build and deploy from a Git repository"** and choose your repository (`plc-attendance-system`).
4. Configure the service settings:
   - **Name**: `plc-attendance` *(your live URL will be `https://plc-attendance.onrender.com`)*
   - **Region**: Choose the closest region (e.g., `Frankfurt` or `Ohio`)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt && python seed.py
     ```
   - **Start Command**:
     ```bash
     gunicorn wsgi:app
     ```
   - **Instance Type**: Select **Free** ($0/month).

---

### Step 3: Configure Environment Variables

1. Scroll down to **"Advanced"** &rarr; click **"Add Environment Variable"**.
2. Add the following keys:
   - **`SECRET_KEY`**: A secure random secret string (e.g. `0b8674fe999b4bc248a5070c223c267e`).
   - **`SESSION_WINDOW_MINUTES`**: `30` (or your preferred check-in window).
3. Click **"Deploy Web Service"**.

Render will now build your application, execute `seed.py` to create the initial database with test users, and launch Gunicorn. Once deployed, you can access your site at the provided `.onrender.com` URL.

---

## Option 2: PythonAnywhere (Dedicated Python Cloud)

[PythonAnywhere](https://www.pythonanywhere.com) is tailored specifically for Python Flask/Django apps. Its free tier provides permanent file storage for SQLite without ephemeral resets.

### Step 1: Create a Free Account
1. Sign up for a free Beginner account at [pythonanywhere.com](https://www.pythonanywhere.com).
2. Your website will be available at: `https://<your-username>.pythonanywhere.com`.

---

### Step 2: Clone Code & Configure Virtual Environment

1. From the dashboard, open a **Bash Console**.
2. Clone your GitHub repository:
   ```bash
   git clone https://github.com/<your-github-username>/plc-attendance-system.git
   cd plc-attendance-system
   ```
3. Set up a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   python seed.py
   ```

---

### Step 3: Configure Web App Settings

1. Go to the **"Web"** tab in the PythonAnywhere dashboard.
2. Click **"Add a new web app"** &rarr; Select **"Manual configuration"** &rarr; Select **Python 3.10** (or latest).
3. Under the **Virtualenv** section, set the path:
   ```text
   /home/<your-username>/plc-attendance-system/venv
   ```
4. Under the **Code** section, click on the **WSGI configuration file** link (e.g. `/var/www/<username>_pythonanywhere_com_wsgi.py`).
5. Replace the entire contents of that file with:
   ```python
   import sys
   import os

   path = '/home/<your-username>/plc-attendance-system'
   if path not in sys.path:
       sys.path.insert(0, path)

   from app import create_app
   application = create_app()
   ```
   *(Be sure to replace `<your-username>` with your actual PythonAnywhere username)*
6. Save the file.
7. Return to the **Web** tab and click **"Reload <your-username>.pythonanywhere.com"**.

---

## Default Login Credentials (After First Deploy)

When `seed.py` runs, it seeds the initial test accounts:

| Role | Email | Password | Permissions |
| :--- | :--- | :--- | :--- |
| **Administrator / Coordinator** | `a.boateng@nyakoa-shs.edu.gh` | `AdminPass123` | Session Management, Directory Approvals, GPS Settings, Audits |
| **Teacher / Faculty** | `k.owusu@nyakoa-shs.edu.gh` | `TeacherPass123` | Mobile OTP Check-in, Geofencing, Attendance History |

---

## Production Security & Maintenance Tips

1. **Change Default Passwords**: After deploying, immediately log in as admin and update default passwords or create fresh credentials in the `/admin/users` directory.
2. **Account Approvals**: Any new user who registers on the live site will require administrator approval in `/admin/users` before they can log in.
3. **Database Backups**:
   - For Render: Render free instances spin down after 15 minutes of inactivity (taking ~30 seconds to wake up on the next request).
   - If you require persistent data storage across container rebuilds on Render, you can connect a free managed PostgreSQL database by setting the `DATABASE_URL` environment variable.
4. **Geolocation on HTTPS**: Browser Geolocation API requires an `https://` connection (provided automatically for free by both Render and PythonAnywhere).
