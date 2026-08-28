from fastapi import FastAPI
from app.routers.auth import router as auth_router

app = FastAPI(title="ClipMind AI")

# Include the authentication test router
app.include_router(auth_router)

@app.get("/")
def read_root():
    return {"message": "Welcome to ClipMind AI Backend!"}
