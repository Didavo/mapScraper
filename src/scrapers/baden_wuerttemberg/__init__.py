"""
Scraper für Baden-Württemberg.
"""

from .hohenlohekreis import (
    MulfingenScraper,
    DoerzbachScraper,
    IngelfingenScraper,
    KuenzelsauScraper,
    ForchtenbergScraper,
    BretzfeldScraper,
    KrautheimScraper,
    KupferzellScraper,
    NeuensteinScraper,
    NiedernhallScraper,
    OehringenScraper,
    PfedelbachScraper,
    SchoentralScraper,
    WaldenburgScraper,
    WeissbachScraper,
    ZweiflingenScraper,
)

from .schwaebisch_hall import (
    BlaufeldenScraper,
    BraunsbachScraper,
    CrailsheimScraper,
    GaildorfScraper,
    GerabronnScraper,
    LangenburgScraper,
    MainhardtScraper,
    MichelfeldScraper,
    SchrozbergScraper,
    SchwaebischHallScraper,
    UntermuenkheimScraper,
)

from .main_tauber_kreis import (
    BadMergentheimScraper,
    BoxbergScraper,
    CrelingenScraper,
    IgersheimScraper,
    NiederstettenScraper,
    WeikersheimScraper,
)

__all__ = [
    # Hohenlohekreis
    "MulfingenScraper",
    "DoerzbachScraper",
    "IngelfingenScraper",
    "KuenzelsauScraper",
    "ForchtenbergScraper",
    "BretzfeldScraper",
    "KrautheimScraper",
    "KupferzellScraper",
    "NeuensteinScraper",
    "NiedernhallScraper",
    "OehringenScraper",
    "PfedelbachScraper",
    "SchoentralScraper",
    "WaldenburgScraper",
    "WeissbachScraper",
    "ZweiflingenScraper",
    # Schwäbisch Hall
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
    # Main-Tauber-Kreis
    "BadMergentheimScraper",
    "BoxbergScraper",
    "CrelingenScraper",
    "IgersheimScraper",
    "NiederstettenScraper",
    "WeikersheimScraper",
]
