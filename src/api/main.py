"""
FastAPI REST API für den Event Scraper.
"""

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.config import get_settings
from .routers import events, locations, sources, scraper, scrape_logs
from .views import pages

settings = get_settings()

# Swagger Docs: hinter Caddy Basic Auth sichtbar, aber nicht extra exponiert
app = FastAPI(
    title="Event Scraper API",
    description="API zum Verwalten und Anzeigen von gescrapten Events",
    version="1.0.0",
)

# CORS - aus Settings laden
cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates
templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

# API Routers
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(locations.router, prefix="/api/locations", tags=["Locations"])
app.include_router(sources.router, prefix="/api/sources", tags=["Sources"])
app.include_router(scraper.router, prefix="/api/scraper", tags=["Scraper"])
app.include_router(scrape_logs.router, prefix="/api/scrape-logs", tags=["Scrape Logs"])

# HTML Views
app.include_router(pages.router, tags=["Pages"])


@app.get("/api")
def api_root():
    """API Übersicht."""
    return {
        "message": "Event Scraper API",
        "endpoints": {
            "events": "/api/events",
            "locations": "/api/locations",
            "sources": "/api/sources",
            "scraper": "/api/scraper",
            "scrape_logs": "/api/scrape-logs",
        },
        "docs": "/docs",
    }
