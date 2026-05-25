from app import app

# This entrypoint is loaded by production WSGI servers like Gunicorn or Waitress.
# It imports the Flask app instance from app.py and exposes it.
if __name__ == "__main__":
    app.run()
