"""Rapprochement alertes ANSM -> Code_CIS (le fichier ANSM n'a pas de CIS).
Méthode : on compare le NOM du produit (avant la 1re virgule) aux dénominations BDPM.
  1. tous les mots du nom ANSM présents dans le nom BDPM          -> 'nom_complet'
  2. sinon, le mot le plus rare du nom ANSM                         -> 'nom_partiel' (confiance faible)
  3. affinage par dosage (nombres) puis par forme pharmaceutique si possible
Résultat : DataFrame (Id_Alerte, Code_CIS, Score_confiance, Methode) + liste des alertes non rapprochées."""
import re
from collections import defaultdict
import pandas as pd
from common import norm

STOP = {"specialites", "base", "gelule", "comprime", "solution", "poudre", "injectable", "importation", "pelliculé","tous", "tout", "dosages", "dosage", "mg", "ml", "ui", "pour", "cent", "mcg", "microgrammes", "gramme",
        "et", "de", "du", "des", "la", "le", "les", "en", "sur", "avec", "ap", "hp", "g", "l", "kg", "mmol", "meq",
        "ml", "mui", "ch", "dh", "mmol"}
MAX_CANDIDATS = 100


def _nom(denomination: str) -> str:
    return denomination.split(",", 1)[0]


def _mots(txt: str) -> set:
    return {t for t in norm(txt).split() if t.isalpha() and len(t) >= 3 and t not in STOP}


def _nombres(txt: str) -> set:
    return {n.replace(",", ".") for n in re.findall(r"\d+(?:,\d+)?", txt)}


def construire_index(med: pd.DataFrame):
    inv, info = defaultdict(set), {}
    for cis, den, forme, statut in zip(med["Code_CIS"], med["Denomination_medicament"],
                                       med["Forme_pharmaceutique"], med["Statut_AMM"]):
        mots = _mots(_nom(den))
        info[cis] = {"mots": mots, "nombres": _nombres(den), "forme": norm(forme), "actif": statut == "Autorisation active"}
        for m in mots:
            inv[m].add(cis)
    return inv, info


def _forme_ansm(titre_complet: str) -> str:
    return norm(titre_complet.split(",", 1)[1]) if "," in titre_complet else ""


def rapprocher(alertes: pd.DataFrame, med: pd.DataFrame):
    inv, info = construire_index(med)
    lignes, non_rapprochees = [], []
    for a in alertes.itertuples():
        mots_a, nb_a = _mots(_nom(a.Nom_produit)), _nombres(_nom(a.Nom_produit))
        if not any(m in inv for m in mots_a):
            non_rapprochees.append((a.Id_Alerte, a.Titre, "aucun mot trouvé dans la BDPM")); continue
        cand = set.intersection(*(inv[m] for m in mots_a)) if all(m in inv for m in mots_a) else set()
        methode, score = "nom_complet", 0.9
        if not cand:
            # repli : on n'accepte qu'un mot qui est le 1er mot du nom (marque) ou une substance citée par l'ANSM
            premier = (norm(_nom(a.Nom_produit)).split() or [""])[0]
            subst = set(norm(a.Substances or "").split())
            sures = sorted((m for m in mots_a if m in inv and (m == premier or m in subst)), key=lambda m: len(inv[m]))
            if not sures:
                non_rapprochees.append((a.Id_Alerte, a.Titre, "nom incertain (aucun mot fiable)")); continue
            cand, methode, score = set(inv[sures[0]]), "nom_partiel", 0.5
        actifs = {c for c in cand if info[c]["actif"]}
        cand = actifs or cand
        if nb_a:
            avec_dosage = {c for c in cand if nb_a <= info[c]["nombres"]}
            if avec_dosage:
                cand, methode, score = avec_dosage, methode + "+dosage", min(1.0, score + 0.1)
            else:
                score -= 0.2
        forme_a = _forme_ansm(a.Nom_produit)
        if forme_a:
            avec_forme = {c for c in cand if info[c]["forme"] and (info[c]["forme"] in forme_a or forme_a.startswith(info[c]["forme"]))}
            if avec_forme and len(avec_forme) < len(cand):
                cand, methode = avec_forme, methode + "+forme"
        if len(cand) > MAX_CANDIDATS:
            non_rapprochees.append((a.Id_Alerte, a.Titre, f"trop ambigu ({len(cand)} CIS)")); continue
        for c in sorted(cand):
            lignes.append((a.Id_Alerte, c, round(max(score, 0.1), 2), methode))
    liens = pd.DataFrame(lignes, columns=["Id_Alerte", "Code_CIS", "Score_confiance", "Methode"])
    rejets = pd.DataFrame(non_rapprochees, columns=["Id_Alerte", "Titre", "Raison"])
    return liens, rejets

