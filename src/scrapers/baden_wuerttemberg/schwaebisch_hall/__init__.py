"""
Scraper für den Landkreis Schwäbisch Hall (Baden-Württemberg).
"""

from .blaufelden import BlaufeldenScraper
from .braunsbach import BraunsbachScraper
from .crailsheim import CrailsheimScraper
from .gaildorf import GaildorfScraper
from .gerabronn import GerabronnScraper
from .langenburg import LangenburgScraper
from .mainhardt import MainhardtScraper
from .michelfeld import MichelfeldScraper
from .schwaebisch_hall import SchwaebischHallScraper
from .untermuenkheim import UntermuenkheimScraper
from .schrozberg import SchrozbergScraper

__all__ = [
    "BlaufeldenScraper",
    "BraunsbachScraper",
    "CrailsheimScraper",
    "GaildorfScraper",
    "GerabronnScraper",
    "LangenburgScraper",
    "MainhardtScraper",
    "MichelfeldScraper",
    "SchrozbergScraper",
    "SchwaebischHallScraper",
    "UntermuenkheimScraper",
]
