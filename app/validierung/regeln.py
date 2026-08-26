from app.modelle import UnternehmenEingabe


class Validierungsfehler(ValueError):
    pass


def validiere_unternehmen(eingabe: UnternehmenEingabe, gueltige_gebiete: set[str]) -> None:
    if not eingabe.name.strip():
        raise Validierungsfehler("Bitte geben Sie einen Unternehmensnamen ein.")
    if not eingabe.pps_nummer.strip():
        raise Validierungsfehler("Bitte geben Sie eine PPS-Nummer ein.")
    if not eingabe.gebiete_je_gewerk:
        raise Validierungsfehler("Bitte wählen Sie mindestens ein Gewerk aus.")
    for gewerk, gebiete in eingabe.gebiete_je_gewerk.items():
        if not gewerk.strip():
            raise Validierungsfehler("Ein Gewerk hat keinen Namen.")
        if not gebiete:
            raise Validierungsfehler(f"Bitte wählen Sie für „{gewerk}“ mindestens ein Gebiet aus.")
        unbekannt = gebiete - gueltige_gebiete
        if unbekannt:
            raise Validierungsfehler(f"Unbekannte Gebietsschlüssel: {', '.join(sorted(unbekannt))}.")
