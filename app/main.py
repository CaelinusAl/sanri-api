from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok", "service": "SANRI API"}

@app.get("/health")
def health():
    return {"status": "ok"}