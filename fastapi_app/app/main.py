import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import region

app = FastAPI(
    title="DevHire Insight API",
    description="채용 공고 지역×스킬 분석 API",
    version="0.1.0",
)

_cors = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(region.router)


@app.get("/health")
def health():
    return {"status": "ok"}
