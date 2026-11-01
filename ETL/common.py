"""Constantes et utilitaires partagés."""
import re, unicodedata, hashlib
from pathlib import Path

ENCODAGE_BDPM = "cp1252"      # fichiers BDPM : texte tabulé, sans en-tête, encodage Windows
SEP_BDPM = "\t"

def norm(texte) -> str:
    """minuscules, sans accents, ponctuation -> espace. Sert à la recherche et au rapprochement."""
    if texte is None:
        return ""
    s = unicodedata.normalize("NFD", str(texte).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def sha256_fichier(chemin) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()

def trouver(dossier: Path, *motifs):
    """Premier fichier du dossier correspondant à un des motifs glob (insensible aux doublons de téléchargement)."""
    for m in motifs:
        r = sorted(Path(dossier).glob(m))
        if r:
            return r[0]
    return None
