from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .elasticsearch_client import get_elasticsearch_client
from .routes import auth as auth_routes
from .routes import notes as notes_routes
from .routes import reviews as reviews_routes


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Saraswati Knowledge Notes", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes FIRST before static files
    app.include_router(notes_routes.router, prefix=settings.api_prefix)
    app.include_router(reviews_routes.router, prefix=settings.api_prefix)
    app.include_router(auth_routes.router, prefix=settings.api_prefix)

    @app.get("/health", tags=["health"])
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    # Static files and SPA fallback routes come LAST
    static_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    frontend_base = settings.frontend_base_path.strip()
    if not frontend_base:
        frontend_base = "/"
    if not frontend_base.startswith("/"):
        frontend_base = f"/{frontend_base}"
    frontend_base = frontend_base.rstrip("/") or "/"

    if static_dir.exists():
        # Serve static assets (JS, CSS, images) directly
        assets_path = static_dir / "assets"
        if assets_path.exists():
            app.mount(f"{frontend_base}/assets", StaticFiles(directory=assets_path), name="assets")

        # SPA fallback for all other frontend routes
        @app.get(frontend_base, include_in_schema=False)
        @app.get(f"{frontend_base}/", include_in_schema=False)
        @app.get(f"{frontend_base}/{{full_path:path}}", include_in_schema=False)
        async def serve_spa(full_path: str = "") -> HTMLResponse:  # type: ignore[override]
            # Only serve index.html for non-API routes
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API endpoint not found")
            
            index_path = static_dir / "index.html"
            if not index_path.exists():
                raise HTTPException(status_code=404, detail="Frontend build missing")
            return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @app.on_event("startup")
    async def _startup() -> None:
        # Warm up the Elasticsearch client so failures surface early
        get_elasticsearch_client(settings)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        client = get_elasticsearch_client(settings)
        await client.close()

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)