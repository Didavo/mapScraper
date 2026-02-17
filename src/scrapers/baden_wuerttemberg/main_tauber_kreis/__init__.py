"""
Scraper für den Main-Tauber-Kreis.
"""

from .bad_mergentheim import BadMergentheimScraper
from .boxberg import BoxbergScraper
from .igersheim import IgersheimScraper
from .niederstetten import NiederstettenScraper
from .weikersheim import WeikersheimScraper
from .creglingen import CrelingenScraper

__all__ = [
    "BadMergentheimScraper",
    "BoxbergScraper",
    "CrelingenScraper",
    "IgersheimScraper",
    "NiederstettenScraper",
    "WeikersheimScraper",
]
