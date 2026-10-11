import os
from dotenv import load_dotenv
load_dotenv()
from app import create_app

app = create_app()

if __name__ == "__main__":
    from waitress import serve
    from app.tasks import Worker
    worker = Worker(app)
    worker.start()
    try:
        serve(app, host=os.environ.get("HOST", "127.0.0.1"),
              port=int(os.environ.get("PORT", "5055")), threads=16)
    finally:
        worker.stop()
