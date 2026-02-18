from fastapi import FastAPI
from app.routers import jobs

app = FastAPI()

app.include_router(jobs.router, prefix="/jobs")

@app.get("/health")
def health():
    return {"status": "ok"}
