"""Contrôle qualité sur la base chargée.  python quality_checks.py --db substimed.db
Sortie : tableau récapitulatif + logs/qualite_<contrôle>.csv (détail des lignes en anomalie)."""
import argparse, sqlite3, sys
from pathlib import Path
import pandas as pd

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DOSSIER_SCRIPT = Path(__file__).resolve().parent
RACINE_ETL = DOSSIER_SCRIPT.parent
RACINE_PROJET = RACINE_ETL.parent

def _trouver_db() -> Path:
    candidats = [
        RACINE_PROJET / "database" / "substimed.db",
        RACINE_ETL / "substimed.db",
        DOSSIER_SCRIPT / "substimed.db",
        DOSSIER_SCRIPT / "data_sample" / "substimed_sample.db",
    ]
    for c in candidats:
        if c.exists():
            return c
    return RACINE_PROJET / "database" / "substimed.db"

def ean13_valide(code: str) -> bool:
    if not code or len(code) != 13 or not code.isdigit():
        return False
    s = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(code[:12]))
    return (10 - s % 10) % 10 == int(code[12])

# (id, gravité, description, SQL renvoyant les lignes en anomalie)
CONTROLES = [
 # ---- doublons
 ("dbl_cis_denomination", "info", "Dénomination identique pour des CIS différents (normal si homonymes)",
  "SELECT Denomination_medicament, COUNT(*) n, GROUP_CONCAT(Code_CIS) cis FROM MEDICAMENT GROUP BY Denomination_norm HAVING n>1"),
 ("dbl_cip7", "erreur", "Code_CIP7 partagé par plusieurs présentations",
  "SELECT Code_CIP7, COUNT(*) n FROM PRESENTATION WHERE Code_CIP7 IS NOT NULL GROUP BY Code_CIP7 HAVING n>1"),
 ("dbl_alerte_meme_cis", "erreur", "Même CIS, même statut, même date de début dans des fiches ANSM différentes (vrai doublon)",
  """SELECT COALESCE(Code_CIS_source, Titre) cle, Statut_Code, Date_Debut, COUNT(DISTINCT URL_Information) nb_fiches
     FROM RUPTURE_ANSM GROUP BY COALESCE(Code_CIS_source, Titre), COALESCE(Code_CIP13_source, ''), Statut_Code, Date_Debut HAVING nb_fiches > 1"""),
 ("dbl_alertes_actives_cis", "avertissement", "CIS avec plusieurs alertes ouvertes (RS/TA) simultanées",
  """SELECT ac.Code_CIS, COUNT(*) n, GROUP_CONCAT(r.Statut_Code) statuts FROM ALERTE_CIS ac JOIN RUPTURE_ANSM r USING (Id_Alerte)
     WHERE r.Statut_Code IN ('RS','TA') GROUP BY ac.Code_CIS HAVING n>1"""),
 # ---- CIS / alertes
 ("alerte_sans_cis", "avertissement", "Alertes sans lien vers MEDICAMENT (CIS absent de CIS_bdpm, ou non rapproché pour l'export web)",
  "SELECT Id_Alerte, Titre, Statut_Code, Code_CIS_source FROM RUPTURE_ANSM WHERE Id_Alerte NOT IN (SELECT Id_Alerte FROM ALERTE_CIS)"),
 ("alerte_confiance_faible", "avertissement", "Alertes dont le rapprochement est peu fiable (score < 0.6)",
  """SELECT r.Id_Alerte, r.Titre, MIN(ac.Score_confiance) score, COUNT(*) nb_cis FROM ALERTE_CIS ac JOIN RUPTURE_ANSM r USING (Id_Alerte)
     GROUP BY r.Id_Alerte HAVING score < 0.6"""),
 ("cis_sans_alerte", "info", "CIS commercialisés sans aucune alerte (attendu pour l'immense majorité)",
  """SELECT Code_CIS, Denomination_medicament FROM MEDICAMENT WHERE Etat_commercialisation='Commercialisée'
     AND Code_CIS NOT IN (SELECT Code_CIS FROM ALERTE_CIS)"""),
 ("cis_alerte_ouverte_non_commercialise", "avertissement", "CIS 'Non commercialisée' en BDPM mais sous alerte RS/TA ouverte",
  """SELECT DISTINCT m.Code_CIS, m.Denomination_medicament, r.Statut_Code FROM MEDICAMENT m JOIN ALERTE_CIS ac USING (Code_CIS)
     JOIN RUPTURE_ANSM r USING (Id_Alerte) WHERE m.Etat_commercialisation='Non commercialisée' AND r.Statut_Code IN ('RS','TA')"""),
 ("cis_sans_presentation", "avertissement", "CIS sans aucune présentation (CIP)",
  "SELECT Code_CIS, Denomination_medicament, Statut_AMM FROM MEDICAMENT WHERE Code_CIS NOT IN (SELECT Code_CIS FROM PRESENTATION)"),
 # ---- dates
 ("date_fin_avant_debut", "erreur", "Date_Fin_Prevue antérieure à Date_Debut",
  "SELECT Id_Alerte, Titre, Date_Debut, Date_Fin_Prevue FROM RUPTURE_ANSM WHERE Date_Fin_Prevue < Date_Debut"),
 ("date_maj_avant_creation", "erreur", "Date de mise à jour antérieure à la date de création",
  "SELECT Id_Alerte, Titre, Date_Creation, Date_MAJ_ANSM FROM RUPTURE_ANSM WHERE Date_MAJ_ANSM < Date_Creation"),
 ("date_debut_apres_maj", "avertissement", "Date_Debut postérieure à la dernière mise à jour ANSM (hors date par défaut du 06/10/2023)",
  "SELECT Id_Alerte, Titre, Date_Debut, Date_MAJ_ANSM FROM RUPTURE_ANSM WHERE Date_MAJ_ANSM IS NOT NULL AND Date_Debut > Date_MAJ_ANSM AND Date_Debut <> '2023-10-06'"),
 ("date_debut_par_defaut_2023", "info", "Date_Debut = 06/10/2023 : valeur par défaut des fiches antérieures à cette date, PAS un vrai début de situation",
  "SELECT Id_Alerte, Titre, Date_Debut, Date_MAJ_ANSM FROM RUPTURE_ANSM WHERE Date_Debut = '2023-10-06'"),
 ("fiche_statuts_differents", "info", "Fiches ANSM dont le statut differe selon le CIS (une fiche != un statut)",
  "SELECT URL_Information, COUNT(DISTINCT Statut_Code) nb_statuts, COUNT(*) nb_lignes FROM RUPTURE_ANSM GROUP BY URL_Information HAVING nb_statuts > 1"),
 ("date_future", "avertissement", "Dates ANSM dans le futur (peut être un arrêt de commercialisation planifié)",
  """SELECT Id_Alerte, Titre, Date_Creation, Date_MAJ_ANSM, Date_Debut FROM RUPTURE_ANSM
     WHERE Date_Creation > Date_Dernier_Import OR Date_MAJ_ANSM > Date_Dernier_Import OR Date_Debut > Date_Dernier_Import"""),
 ("rd_sans_date_fin", "avertissement", "Statut 'Remise à disposition' sans date de remise à disposition",
  "SELECT Id_Alerte, Titre FROM RUPTURE_ANSM WHERE Statut_Code='RD' AND Date_Fin_Prevue IS NULL"),
 ("date_fin_sur_alerte_ouverte", "avertissement", "Date de fin renseignée alors que le statut est RS/TA (alerte censée ouverte)",
  "SELECT Id_Alerte, Titre, Statut_Code, Date_Fin_Prevue FROM RUPTURE_ANSM WHERE Statut_Code IN ('RS','TA') AND Date_Fin_Prevue IS NOT NULL"),
 ("date_amm_future", "erreur", "Date d'AMM dans le futur",
  "SELECT Code_CIS, Denomination_medicament, Date_AMM FROM MEDICAMENT WHERE Date_AMM > date('now')"),
 ("date_declaration_future", "erreur", "Date de déclaration de présentation dans le futur",
  "SELECT Code_CIP13, Code_CIS, Date_declaration FROM PRESENTATION WHERE Date_declaration > date('now')"),
 ("date_declaration_avant_amm", "avertissement", "Présentation déclarée avant la date d'AMM du médicament",
  "SELECT p.Code_CIP13, p.Code_CIS, p.Date_declaration, m.Date_AMM FROM PRESENTATION p JOIN MEDICAMENT m USING (Code_CIS) WHERE p.Date_declaration < m.Date_AMM"),
 # ---- identifiants
 ("cip13_cip7_incoherents", "erreur", "CIP13 dont les caractères 6 à 12 ne correspondent pas au CIP7 (CIP13 = 340 + 2 car. + CIP7 + clé)",
  "SELECT Code_CIP13, Code_CIP7 FROM PRESENTATION WHERE Code_CIP7 IS NOT NULL AND substr(Code_CIP13,6,7) <> Code_CIP7"),

 # ---- contrôles liés à COMPO / GENER / signal BDPM
 ("cis_bdm_alerte_sans_fiche", "avertissement", "CIS marqués « Alerte » par la BDPM (StatutBdm) sans fiche ANSM rattachée",
  "SELECT Code_CIS, Denomination_medicament, Etat_commercialisation FROM MEDICAMENT WHERE Statut_BDM='Alerte' AND Code_CIS NOT IN (SELECT Code_CIS FROM ALERTE_CIS)"),
 ("alerte_cip13_inconnu", "avertissement", "Alerte visant un CIP13 absent de CIS_CIP_bdpm (incohérence entre fichiers sources)",
  "SELECT Id_Alerte, Code_CIS, Code_CIP13 FROM ALERTE_CIS WHERE Code_CIP13 <> '' AND Code_CIP13 NOT IN (SELECT Code_CIP13 FROM PRESENTATION)"),
 ("alerte_cip13_autre_cis", "erreur", "Alerte dont le CIP13 n'appartient pas au CIS indiqué",
  "SELECT ac.Id_Alerte, ac.Code_CIS, ac.Code_CIP13 FROM ALERTE_CIS ac JOIN PRESENTATION p ON p.Code_CIP13 = ac.Code_CIP13 WHERE p.Code_CIS <> ac.Code_CIS"),
 ("cis_actif_sans_composition", "avertissement", "CIS à AMM active sans aucune ligne de composition (donc sans substitut possible)",
  "SELECT Code_CIS, Denomination_medicament FROM MEDICAMENT WHERE Statut_AMM='Autorisation active' AND Code_CIS NOT IN (SELECT Code_CIS FROM COMPOSITION)"),
 ("compo_sans_substance_active", "avertissement", "CIS ayant une composition mais aucune substance active (SA)",
  "SELECT Code_CIS FROM COMPOSITION GROUP BY Code_CIS HAVING SUM(Nature='SA') = 0"),
 ("cis_plusieurs_groupes", "info", "CIS dans plusieurs groupes génériques (complémentarité posologique) : cardinalité réelle 0,N",
  "SELECT Code_CIS, COUNT(*) nb_groupes, GROUP_CONCAT(Identifiant_groupe_generique) groupes FROM MEDICAMENT_GROUPE GROUP BY Code_CIS HAVING nb_groupes > 1"),
 ("groupe_sans_princeps", "info", "Groupes génériques sans princeps (type 0) dans la base",
  "SELECT Identifiant_groupe_generique, COUNT(*) nb FROM MEDICAMENT_GROUPE GROUP BY Identifiant_groupe_generique HAVING SUM(Type_generique = 0) = 0"),
 ("alerte_ouverte_sans_substitut", "info", "CIS sous alerte ouverte (RS/TA) sans aucun autre CIS de même groupe générique",
  """SELECT DISTINCT ac.Code_CIS FROM ALERTE_CIS ac JOIN RUPTURE_ANSM r USING (Id_Alerte)
     WHERE r.Statut_Code IN ('RS','TA')
       AND NOT EXISTS (SELECT 1 FROM MEDICAMENT_GROUPE g1 JOIN MEDICAMENT_GROUPE g2 USING (Identifiant_groupe_generique)
                       WHERE g1.Code_CIS = ac.Code_CIS AND g2.Code_CIS <> ac.Code_CIS)"""),
]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(_trouver_db()))
    ap.add_argument("--logs", default=str(RACINE_ETL / "logs"))
    a = ap.parse_args(argv)
    logs = Path(a.logs); logs.mkdir(exist_ok=True)
    if not Path(a.db).exists():
        raise FileNotFoundError(f"Base de données introuvable : {a.db}")
    con = sqlite3.connect(a.db)
    resume = []
    for cid, grav, desc, sql in CONTROLES:
        df = pd.read_sql_query(sql, con)
        resume.append((cid, grav, len(df), desc))
        if len(df):
            df.to_csv(logs / f"qualite_{cid}.csv", index=False, encoding="utf-8-sig")
    # clé EAN-13 des CIP13 (calcul Python, pas SQL)
    cip = pd.read_sql_query("SELECT Code_CIP13, Code_CIS FROM PRESENTATION", con)
    mauvais = cip[~cip["Code_CIP13"].map(ean13_valide)]
    resume.append(("cip13_cle_invalide", "erreur", len(mauvais), "CIP13 dont la clé de contrôle EAN-13 est fausse"))
    if len(mauvais):
        mauvais.to_csv(logs / "qualite_cip13_cle_invalide.csv", index=False, encoding="utf-8-sig")
    con.close()
    rap = pd.DataFrame(resume, columns=["controle", "gravite", "nb_anomalies", "description"])
    rap.to_csv(logs / "qualite_resume.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200, "display.max_colwidth", 90)
    print(rap.to_string(index=False))
    return rap

if __name__ == "__main__":
    main()
