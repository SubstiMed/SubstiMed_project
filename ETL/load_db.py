"""Import REJOUABLE dans la base (SQLite ; transposable PostgreSQL).
    python load_db.py --data-dir ./data --db substimed.db [--date-import 2026-10-27]

Rejouable = idempotent : relancer sur les mêmes fichiers ne crée aucun doublon (UPSERT sur les clés primaires),
et relancer sur des fichiers plus récents met à jour l'existant. Tout se fait dans UNE transaction (tout ou rien).
Historique : RUPTURE_ANSM garde l'état courant ; RUPTURE_HISTORIQUE ajoute une ligne à chaque changement constaté
(statut, date de début, date de fin ; la simple date de mise à jour ANSM n'en crée pas) et n'est jamais purgé. Une alerte qui disparaît du fichier ANSM n'est pas supprimée."""
import argparse, hashlib, sqlite3, sys
from datetime import datetime
from pathlib import Path
import pandas as pd
from common import sha256_fichier, trouver
import clean_bdpm as bd, clean_ansm as an
try:
    import match_ansm as ma
except ImportError:
    ma = None

RACINE_ETL = Path(__file__).resolve().parent
RACINE_PROJET = RACINE_ETL.parent

def _trouver_schema() -> Path:
    candidats = [
        RACINE_PROJET / "database" / "schema.sql",
        RACINE_ETL / "database" / "schema.sql",
        RACINE_ETL / "sql" / "schema.sql",
        RACINE_ETL / "schema.sql",
    ]
    for c in candidats:
        if c.exists():
            return c
    return RACINE_PROJET / "database" / "schema.sql"


def _py(v):
    """None pour les vides ; scalaires numpy -> types Python (sinon SQLite stocke les entiers numpy en BLOB)."""
    if pd.isna(v):
        return None
    return v.item() if hasattr(v, "item") else v


def _lignes(df):
    return [tuple(_py(v) for v in r) for r in df.itertuples(index=False, name=None)]


def upsert(cur, table, df, cle):
    cols = list(df.columns)
    maj = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in cle)
    sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
           f"ON CONFLICT ({', '.join(cle)}) DO " + (f"UPDATE SET {maj}" if maj else "NOTHING"))
    cur.executemany(sql, _lignes(df))


def empreinte(r):
    return hashlib.sha1("|".join(str(r[k]) for k in ("Statut_Code", "Date_Debut", "Date_Fin_Prevue")).encode()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(RACINE_ETL / "data"))
    ap.add_argument("--db", default=str(RACINE_PROJET / "database" / "substimed.db"))
    ap.add_argument("--date-import", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--logs", default=str(RACINE_ETL / "logs"))
    a = ap.parse_args(argv)
    d, logs = Path(a.data_dir), Path(a.logs); logs.mkdir(exist_ok=True)
    Path(a.db).parent.mkdir(parents=True, exist_ok=True)

    f_cis = trouver(d, "CIS_bdpm.txt", "CIS_bdpm.csv", "CIS_bdpm*")
    f_cip = trouver(d, "CIS_CIP_bdpm.txt", "CIS_CIP_bdpm.csv", "CIS_CIP_bdpm*")
    f_ansm = trouver(d, "CIS_CIP_Dispo_Spec.txt", "*Dispo_Spec*", "*disponibilites*.xls*", "*ansm*.xls*", "*ansm*.csv")
    f_compo = trouver(d, "CIS_COMPO_bdpm.txt", "CIS_COMPO_bdpm.csv", "CIS_COMPO_bdpm*")
    f_gener = trouver(d, "CIS_GENER_bdpm.txt", "CIS_GENER_bdpm.csv", "CIS_GENER_bdpm*")
    if not (f_cis and f_cip and f_ansm):
        sys.exit(f"Fichiers manquants dans {d} : CIS={f_cis} CIP={f_cip} ANSM/Dispo_Spec={f_ansm}")
    for f in (f_compo, f_gener):
        if f is None:
            print("⚠ fichier COMPO ou GENER absent : pas d'alternatives de substitution possibles")

    # ---- 1. nettoyage en mémoire (rien n'est écrit en base si une étape échoue)
    med, a1 = bd.nettoyer_cis(f_cis)
    pres, a2 = bd.nettoyer_cip(f_cip, set(med["Code_CIS"]))
    if "_orphelins" in a2:
        a2.pop("_orphelins").to_csv(logs / "rejets_presentations_cis_inconnu.csv", index=False, encoding="utf-8-sig")
    mode = an.type_dispo(f_ansm)
    if mode == "officiel":      # CIS fournis : jointure directe par Code_CIS (+ CIP13)
        alertes, liens, rejets, a3 = an.nettoyer_dispo_officiel(f_ansm, set(med["Code_CIS"]), a.date_import)
    else:                       # export web du site ANSM : pas de CIS -> rapprochement par nom
        alertes, a3 = an.nettoyer_ansm(f_ansm, a.date_import)
        liens, rejets = ma.rapprocher(alertes, med)
        liens["Code_CIP13"] = ""
    rejets.to_csv(logs / "rejets_alertes.csv", index=False, encoding="utf-8-sig")
    print(f"Fichier disponibilité : {f_ansm.name}  (format « {mode} »)")
    print("BDPM CIS  :", a1); print("BDPM CIP  :", {k: v for k, v in a2.items() if k[0] != "_"}); print("Dispo/ANSM:", a3)
    print(f"Alertes liées à un CIS : {liens.Id_Alerte.nunique()}/{len(alertes)}, {len(liens)} liens, {len(rejets)} rejets")

    compo_res = gener_res = None
    if f_compo:
        compo_res = bd.nettoyer_compo(f_compo, set(med["Code_CIS"]))
        print("BDPM COMPO:", {k: v for k, v in compo_res[2].items() if k[0] != "_"})
        if "_orphelins" in compo_res[2]:
            compo_res[2].pop("_orphelins").to_csv(logs / "rejets_compo_cis_inconnu.csv", index=False, encoding="utf-8-sig")
    if f_gener:
        gener_res = bd.nettoyer_gener(f_gener, set(med["Code_CIS"]))
        print("BDPM GENER:", {k: v for k, v in gener_res[2].items() if k[0] != "_"})
        if "_orphelins" in gener_res[2]:
            gener_res[2].pop("_orphelins").to_csv(logs / "rejets_gener_cis_inconnu.csv", index=False, encoding="utf-8-sig")

    # ---- 2. écriture transactionnelle
    con = sqlite3.connect(a.db)
    con.execute("PRAGMA foreign_keys = ON")
    f_schema = _trouver_schema()
    con.executescript(f_schema.read_text(encoding="utf-8"))
    cur = con.cursor()
    try:
        cur.execute("BEGIN")
        upsert(cur, "MEDICAMENT", med, ["Code_CIS"])
        upsert(cur, "PRESENTATION", pres, ["Code_CIP13"])
        if f_compo:
            subst, compo, ac = compo_res
            upsert(cur, "SUBSTANCE", subst, ["Code_substance"])
            upsert(cur, "COMPOSITION", compo, ["Code_CIS", "Designation_element", "Code_substance", "Dosage_substance",
                                               "Reference_dosage", "Nature", "Numero_liaison"])
        if f_gener:
            groupes, lg, ag = gener_res
            upsert(cur, "GROUPE_GENERIQUE", groupes, ["Identifiant_groupe_generique"])
            upsert(cur, "MEDICAMENT_GROUPE", lg, ["Code_CIS", "Identifiant_groupe_generique"])

        deja = {r[0]: r[1:] for r in cur.execute("SELECT Id_Alerte, Statut_Code, Date_Debut, Date_Fin_Prevue, Date_MAJ_ANSM FROM RUPTURE_ANSM")}
        nouvelles = modifiees = 0
        for r in alertes.to_dict("records"):
            r = {k: (None if pd.isna(v) else v) for k, v in r.items()}
            ancien = deja.get(r["Id_Alerte"])
            nouvelles += ancien is None
            modifiees += ancien is not None and ancien[:3] != (r["Statut_Code"], r["Date_Debut"], r["Date_Fin_Prevue"])
            cur.execute("""INSERT INTO RUPTURE_ANSM (Id_Alerte, Titre, Statut_Code, Statut_Libelle, Date_Creation, Date_MAJ_ANSM,
                           Date_Debut, Date_Fin_Prevue, Produit_sante, Domaine_medical, URL_Information, Code_CIS_source, Code_CIP13_source,
                           Date_Premier_Import, Date_Dernier_Import)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT (Id_Alerte) DO UPDATE SET Titre=excluded.Titre, Statut_Code=excluded.Statut_Code,
                           Statut_Libelle=excluded.Statut_Libelle, Date_Creation=excluded.Date_Creation, Date_MAJ_ANSM=excluded.Date_MAJ_ANSM,
                           Date_Debut=excluded.Date_Debut, Date_Fin_Prevue=excluded.Date_Fin_Prevue, Produit_sante=excluded.Produit_sante,
                           Domaine_medical=excluded.Domaine_medical, URL_Information=excluded.URL_Information,
                           Code_CIS_source=excluded.Code_CIS_source, Code_CIP13_source=excluded.Code_CIP13_source,
                           Date_Dernier_Import=excluded.Date_Dernier_Import""",
                        (r["Id_Alerte"], r["Titre"], r["Statut_Code"], r["Statut_Libelle"], r["Date_Creation"], r["Date_MAJ_ANSM"],
                         r["Date_Debut"], r["Date_Fin_Prevue"], r["Produit_sante"], r["Domaine_medical"], r["URL_Information"],
                         r["Code_CIS_source"], r["Code_CIP13_source"], a.date_import, a.date_import))
            # historique : n'insère que si l'empreinte (statut+dates) est nouvelle pour cette alerte
            cur.execute("""INSERT OR IGNORE INTO RUPTURE_HISTORIQUE (Id_Alerte, Statut_Code, Date_Debut, Date_Fin_Prevue, Date_MAJ_ANSM, Date_Import, Empreinte)
                           VALUES (?,?,?,?,?,?,?)""",
                        (r["Id_Alerte"], r["Statut_Code"], r["Date_Debut"], r["Date_Fin_Prevue"], r["Date_MAJ_ANSM"], a.date_import, empreinte(r)))
        # liens alerte->CIS recalculés pour les alertes du fichier courant
        cur.executemany("DELETE FROM ALERTE_CIS WHERE Id_Alerte = ?", [(i,) for i in alertes["Id_Alerte"]])
        cur.executemany("INSERT INTO ALERTE_CIS (Id_Alerte, Code_CIS, Code_CIP13, Score_confiance, Methode) VALUES (?,?,?,?,?)",
                        _lignes(liens[["Id_Alerte", "Code_CIS", "Code_CIP13", "Score_confiance", "Methode"]]))
        cur.execute("INSERT INTO IMPORT_LOG (Date_Import, Source, Sha256, Nb_lignes, Nb_nouvelles, Nb_modifiees) VALUES (?,?,?,?,?,?)",
                    (datetime.now().isoformat(timespec="seconds"), f_ansm.name, sha256_fichier(f_ansm), len(alertes), int(nouvelles), int(modifiees)))
        con.commit()
    except Exception:
        con.rollback(); raise
    finally:
        con.close()
    print(f"OK -> {a.db} | alertes : {nouvelles} nouvelles, {modifiees} modifiées")


if __name__ == "__main__":
    main()
