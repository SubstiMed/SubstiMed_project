"""Jeu d'échantillon (~100 médicaments) tiré de la base complète, pour que l'équipe puisse travailler tout de suite.
    python make_sample.py [--db substimed.db] [--out data_sample] [--n 100]
Contenu : alertes variées (RS/TA/RD/AC) bien rapprochées + leurs CIS + de quoi atteindre N médicaments,
leurs présentations, leurs compositions et groupes génériques (avec des médicaments du même groupe, pour tester une substitution), l'historique, et 1 alerte non rapprochée (cas limite). Génère aussi data_sample/substimed_sample.db."""
import argparse, sqlite3
from pathlib import Path
import pandas as pd

DOSSIER_SCRIPT = Path(__file__).resolve().parent
RACINE_ETL = DOSSIER_SCRIPT.parent
RACINE_PROJET = RACINE_ETL.parent

def _trouver_db() -> Path:
    candidats = [
        RACINE_PROJET / "database" / "substimed.db",
        RACINE_ETL / "substimed.db",
        DOSSIER_SCRIPT / "substimed.db",
    ]
    for c in candidats:
        if c.exists():
            return c
    return RACINE_PROJET / "database" / "substimed.db"

def _trouver_schema() -> Path:
    candidats = [
        RACINE_PROJET / "database" / "schema.sql",
        RACINE_ETL / "database" / "schema.sql",
        RACINE_ETL / "sql" / "schema.sql",
        DOSSIER_SCRIPT / "schema.sql",
    ]
    for c in candidats:
        if c.exists():
            return c
    return RACINE_PROJET / "database" / "schema.sql"

TABLES = ["MEDICAMENT", "PRESENTATION", "SUBSTANCE", "COMPOSITION", "GROUPE_GENERIQUE", "MEDICAMENT_GROUPE",
          "RUPTURE_ANSM", "ALERTE_CIS", "RUPTURE_HISTORIQUE"]

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(_trouver_db()))
    ap.add_argument("--out", default=str(DOSSIER_SCRIPT / "data_sample"))
    ap.add_argument("--n", type=int, default=100)
    a = ap.parse_args(argv)
    out = Path(a.out); out.mkdir(exist_ok=True)
    if not Path(a.db).exists():
        raise FileNotFoundError(f"Base de données source introuvable : {a.db}")
    src = sqlite3.connect(a.db)
    q = lambda s, p=(): pd.read_sql_query(s, src, params=p)

    # 6 alertes par statut, bien rapprochées (score >= 0.8, <= 4 CIS) + 1 alerte sans CIS
    bonnes = q("""SELECT r.Id_Alerte, r.Statut_Code FROM RUPTURE_ANSM r JOIN ALERTE_CIS ac USING (Id_Alerte)
                  GROUP BY r.Id_Alerte HAVING MIN(ac.Score_confiance) >= 0.8 AND COUNT(*) <= 4 ORDER BY r.Id_Alerte""")
    ids = bonnes.groupby("Statut_Code").head(6)["Id_Alerte"].tolist()
    ids += q("SELECT Id_Alerte FROM RUPTURE_ANSM WHERE Id_Alerte NOT IN (SELECT Id_Alerte FROM ALERTE_CIS) ORDER BY Id_Alerte LIMIT 1")["Id_Alerte"].tolist()
    marq = ",".join("?" * len(ids))
    cis = set(q(f"SELECT DISTINCT Code_CIS FROM ALERTE_CIS WHERE Id_Alerte IN ({marq})", ids)["Code_CIS"])
    # + des médicaments du MÊME groupe générique que les CIS en alerte : l'échantillon permet de tester une substitution
    mates = q(f"""SELECT DISTINCT g2.Code_CIS FROM MEDICAMENT_GROUPE g1 JOIN MEDICAMENT_GROUPE g2 USING (Identifiant_groupe_generique)
                  JOIN MEDICAMENT m ON m.Code_CIS = g2.Code_CIS
                  WHERE g1.Code_CIS IN ({",".join("?" * len(cis))}) AND g2.Code_CIS NOT IN ({",".join("?" * len(cis))})
                  AND m.Statut_AMM='Autorisation active' AND g2.Code_CIS IN (SELECT Code_CIS FROM PRESENTATION)
                  ORDER BY g2.Code_CIS""", sorted(cis) * 2)["Code_CIS"].tolist()
    cis |= set(mates[: max(0, (a.n - len(cis)) * 2 // 3)])
    reste = max(0, a.n - len(cis))
    # compléter avec des médicaments commercialisés ayant des présentations (graine fixe -> échantillon reproductible)
    comp = q("""SELECT Code_CIS FROM MEDICAMENT WHERE Etat_commercialisation='Commercialisée' AND Statut_AMM='Autorisation active'
                AND Code_CIS IN (SELECT Code_CIS FROM PRESENTATION)""").sample(n=reste, random_state=42)["Code_CIS"]
    cis |= set(comp)
    mc = ",".join("?" * len(cis)); lc = sorted(cis)

    dst_path = out / "substimed_sample.db"
    dst_path.unlink(missing_ok=True)
    dst = sqlite3.connect(dst_path)
    f_schema = _trouver_schema()
    dst.executescript(f_schema.read_text(encoding="utf-8"))
    jeux = {
        "MEDICAMENT": q(f"SELECT * FROM MEDICAMENT WHERE Code_CIS IN ({mc}) ORDER BY Code_CIS", lc),
        "PRESENTATION": q(f"SELECT * FROM PRESENTATION WHERE Code_CIS IN ({mc}) ORDER BY Code_CIP13", lc),
        "SUBSTANCE": q(f"SELECT * FROM SUBSTANCE WHERE Code_substance IN (SELECT Code_substance FROM COMPOSITION WHERE Code_CIS IN ({mc})) ORDER BY Code_substance", lc),
        "COMPOSITION": q(f"SELECT * FROM COMPOSITION WHERE Code_CIS IN ({mc}) ORDER BY Id_composition", lc),
        "GROUPE_GENERIQUE": q(f"SELECT * FROM GROUPE_GENERIQUE WHERE Identifiant_groupe_generique IN (SELECT Identifiant_groupe_generique FROM MEDICAMENT_GROUPE WHERE Code_CIS IN ({mc}))", lc),
        "MEDICAMENT_GROUPE": q(f"SELECT * FROM MEDICAMENT_GROUPE WHERE Code_CIS IN ({mc})", lc),
        "RUPTURE_ANSM": q(f"SELECT * FROM RUPTURE_ANSM WHERE Id_Alerte IN ({marq}) ORDER BY Id_Alerte", ids),
        "ALERTE_CIS": q(f"SELECT * FROM ALERTE_CIS WHERE Id_Alerte IN ({marq}) AND Code_CIS IN ({mc})", ids + lc),
        "RUPTURE_HISTORIQUE": q(f"SELECT * FROM RUPTURE_HISTORIQUE WHERE Id_Alerte IN ({marq})", ids),
    }
    for t in TABLES:                                   # ordre = respect des clés étrangères
        df = jeux[t]
        df.to_sql(t, dst, if_exists="append", index=False)
        df.to_csv(out / f"{t.lower()}.csv", index=False, encoding="utf-8-sig")
        print(f"{t:20s} {len(df):4d} lignes")
    dst.commit(); dst.close(); src.close()
    
    # Copie pratique également dans database/ pour l'équipe
    db_dest = RACINE_PROJET / "database" / "substimed_sample.db"
    if db_dest.parent.exists():
        import shutil
        shutil.copy2(dst_path, db_dest)
        print(f"Échantillon copié également dans {db_dest}")

if __name__ == "__main__":
    main()
