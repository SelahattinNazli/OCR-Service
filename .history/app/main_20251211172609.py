from fastapi import FastAPI
from app.routers import ocr_router
# from app.config import settings

app = FastAPI(
    title="OCR Service",
    description="FastAPI based OCR service with EasyOCR and LLM support",
    version="0.1.0",
)

# Include routers
app.include_router(ocr_router.router, prefix="/api", tags=["OCR"])


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
