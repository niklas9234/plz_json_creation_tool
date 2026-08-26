from dataclasses import dataclass, field


@dataclass(frozen=True)
class UnternehmenEingabe:
    name: str
    pps_nummer: str
    aktiv: bool = True
    gebiete_je_gewerk: dict[str, set[str]] = field(default_factory=dict)
