from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.auth import router as auth_router
from app.routers.video import router as video_router
from app.routers.key_moment import router as key_moment_router


app = FastAPI(title="ClipMind AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the authentication test router
app.include_router(auth_router)
app.include_router(video_router)
app.include_router(key_moment_router)
@app.get("/")
def read_root():
    return {"message": "Welcome to ClipMind AI Backend!"}
