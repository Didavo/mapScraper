from .base import BaseScraper, ScrapedEvent

# Baden-Württemberg - Hohenlohekreis
from .baden_wuerttemberg.hohenlohekreis import (
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

# Baden-Württemberg - Schwäbisch Hall
from .baden_wuerttemberg.schwaebisch_hall import (
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

# Baden-Württemberg - Main-Tauber-Kreis
from .baden_wuerttemberg.main_tauber_kreis import (
    BadMergentheimScraper,
    BoxbergScraper,
    CrelingenScraper,
    IgersheimScraper,
    NiederstettenScraper,
    WeikersheimScraper,
)

__all__ = [
    "BaseScraper",
    "ScrapedEvent",
    # Baden-Württemberg - Hohenlohekreis
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
    # Baden-Württemberg - Schwäbisch Hall
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
    # Baden-Württemberg - Main-Tauber-Kreis
    "BadMergentheimScraper",
    "BoxbergScraper",
    "CrelingenScraper",
    "IgersheimScraper",
    "NiederstettenScraper",
    "WeikersheimScraper",
]
