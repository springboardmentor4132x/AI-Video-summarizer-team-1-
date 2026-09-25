
from fastapi.middleware.cors import CORSMiddleware

from app.routers.auth import router as auth_router
from app.routers.videos import router as videos_router
from app.routers.key_moment import router as key_moment_router
from app.routers.transcript import router as transcript_router
from app.routers.summary import router as summary_router
from app.routers.admin import router as admin_router
from app.routers.analytics import router as analytics_router

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

# Include application routers
app.include_router(auth_router)
app.include_router(videos_router)
app.include_router(key_moment_router)
app.include_router(transcript_router)
app.include_router(summary_router)
app.include_router(admin_router)
app.include_router(analytics_router)

@app.get("/")
def read_root():
    return {"message": "Welcome to ClipMind AI Backend!"}