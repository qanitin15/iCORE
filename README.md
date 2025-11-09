# iCORE — Running in production

This repository contains a Flask backend (`backend.py`) and a simple single-page frontend (`iCOREapp.html` + templates).

There are two recommended ways to run the app as a proper service (not the Flask dev server):

1) Run with Waitress on Windows (recommended for local testing)

   - Create and activate your virtualenv (PowerShell):

     ```powershell
     py -3 -m venv .venv
     .\.venv\Scripts\Activate.ps1
     pip install -r requirements.txt
     ```

   - Run with Waitress (bind to 0.0.0.0 so other devices can reach it):

     ```powershell
     python -m waitress --port=5000 backend:app
     ```

   - Visit http://localhost:5000 or http://127.0.0.1:5000

2) Run with Docker (production-like, uses Gunicorn)

   - Build the image:

     ```powershell
     docker build -t icore:latest .
     ```

   - Run the container:

     ```powershell
     docker run -p 5000:5000 icore:latest
     ```

   - Visit http://localhost:5000

Notes
- The dev server (`python backend.py`) is fine for development but not recommended for production.
- The `requirements.txt` contains `waitress` and `gunicorn` so either option will work.
# iCORE Flask Backend

This is a small Flask backend for the iCORE project.

Prerequisites
- Python 3.8+ must be installed and accessible as `python` in your PATH.

Quick start (PowerShell):

```powershell
# create a virtual environment
python -m venv .venv; .\.venv\Scripts\Activate.ps1
# install dependencies
python -m pip install -r requirements.txt
# run the app
python backend.py
```

If `python` is not found, install Python from https://www.python.org/downloads/ and ensure the "Add to PATH" option is checked.
