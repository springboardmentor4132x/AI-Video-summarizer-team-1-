from fastapi import FastAPI

from app.routers.auth import router as auth_router
from app.routers.videos import router as videos_router

app = FastAPI(title="ClipMind AI")

app.include_router(auth_router)
app.include_router(videos_router)


@app.get("/")
def read_root():
    return {"message": "Welcome to ClipMind AI Backend!"}
