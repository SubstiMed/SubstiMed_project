"""Nettoyage du fichier ANSM (export « disponibilités des médicaments », .xls/.xlsx/.csv).
ATTENTION : ce fichier n'a PAS de Code_CIS ; la jointure avec la BDPM se fait ensuite par nom (match_ansm.py)."""
import hashlib, re, shutil, subprocess, tempfile
from pathlib import Path
import pandas as pd

STATUTS = {"rupture de stock": "RS", "tension d'approvisionnement": "TA",
           "remise à disposition": "RD", "arrêt de commercialisation": "AC"}
RENOMMAGE = {"Titre": "Titre", "Date de création": "Date_Creation", "Date de mise à jour": "Date_MAJ_ANSM",
             "Date de début de situation": "Date_Debut", "Date de remise à disposition": "Date_Fin_Prevue",
             "Statut": "Statut_Libelle", "Produit(s) de santé": "Produit_sante",
             "Domaine(s) médical(aux)": "Domaine_medical", "URL de la page": "URL_Information"}


def lire_ansm(chemin) -> pd.DataFrame:
    chemin = Path(chemin)
    ext = chemin.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(chemin, sep=None, engine="python", encoding="utf-8-sig", dtype=str)
    if ext == ".xlsx":
        return pd.read_excel(chemin, dtype=str)
    # .xls : l'export ANSM est souvent « corrompu » pour xlrd -> calamine le lit ; repli LibreOffice
    for moteur in ("calamine", "xlrd"):
        try:
            return pd.read_excel(chemin, engine=moteur, dtype=str)
        except Exception as e:                       # noqa: BLE001
            derniere = e
    if shutil.which("soffice"):
        with tempfile.TemporaryDirectory() as t:
            subprocess.run(["soffice", "--headless", "--convert-to", "xlsx", "--outdir", t, str(chemin)], check=True)
            return pd.read_excel(Path(t) / (chemin.stem + ".xlsx"), dtype=str)
    raise RuntimeError(f"Impossible de lire {chemin} ({derniere}). pip install python-calamine, "
                       "ou ré-enregistrer le fichier en .xlsx.")


def _id_alerte(url: str) -> str:
    return "ANSM-" + hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:12]


def _decouper_titre(titre: str):
    """'Brevibloc 100 mg/10 ml, solution … – [esmolol]' -> (nom produit, substances)"""
    m = re.match(r"^(.*?)\s*\|?\s*[–-]\s+\[(.*)\]\*?\s*$", titre, flags=re.S)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return titre.strip().rstrip("*").strip(), None


def nettoyer_ansm(chemin, date_import=None):
    brut = lire_ansm(chemin)
    brut.columns = [str(c).strip() for c in brut.columns]
    manquantes = set(RENOMMAGE) - set(brut.columns)
    if manquantes:
        raise ValueError(f"Colonnes ANSM absentes : {sorted(manquantes)}")
    df = brut.rename(columns=RENOMMAGE)[list(RENOMMAGE.values())].copy()
    anomalies = {"lignes_lues": len(df)}
    for c in df.columns:
        df[c] = df[c].astype("string").str.replace("\u00a0", " ", regex=False).str.strip().replace("", pd.NA)
    for c in ("Date_Creation", "Date_MAJ_ANSM", "Date_Debut", "Date_Fin_Prevue"):
        parsed = pd.to_datetime(df[c], errors="coerce", format="mixed", dayfirst=False)
        anomalies[f"{c}_illisibles"] = int((parsed.isna() & df[c].notna()).sum())
        df[c] = parsed.dt.strftime("%Y-%m-%d")
    df["Statut_Code"] = df["Statut_Libelle"].str.lower().map(STATUTS)
    anomalies["statuts_inconnus"] = int(df["Statut_Code"].isna().sum())
    df = df.dropna(subset=["Titre", "URL_Information", "Statut_Code", "Date_Debut"])
    anomalies["doublons_url_supprimes"] = int(df["URL_Information"].duplicated().sum())
    df = df.drop_duplicates("URL_Information", keep="last")
    df["Id_Alerte"] = df["URL_Information"].map(_id_alerte)
    parts = df["Titre"].map(_decouper_titre)
    df["Nom_produit"] = parts.str[0]
    df["Substances"] = parts.str[1]
    df["Date_Import"] = date_import or pd.Timestamp.today().strftime("%Y-%m-%d")
    df["Code_CIS_source"] = None
    df["Code_CIP13_source"] = None
    cols = ["Id_Alerte", "Titre", "Nom_produit", "Substances", "Statut_Code", "Statut_Libelle", "Date_Creation",
            "Date_MAJ_ANSM", "Date_Debut", "Date_Fin_Prevue", "Produit_sante", "Domaine_medical",
            "URL_Information", "Code_CIS_source", "Code_CIP13_source", "Date_Import"]
    return df[cols].reset_index(drop=True), anomalies


# ---------------------------------------------------------------------------------------------------------------
# FICHIER OFFICIEL BDPM « CIS_CIP_Dispo_Spec » (doc BDPM §3.10) : tabulé, sans en-tête, AVEC Code_CIS (et CIP13 facultatif).
# Colonnes : CIS | CIP13 (vide si toutes les présentations sont concernées) | code statut | libellé | date début |
#            date MAJ | date remise à disposition | lien ANSM.   Codes : 1 RS, 2 TA, 3 AC, 4 RD.
# ⚠ Écrit d'après la documentation, testé sur un fichier fabriqué au format documenté (pas sur un vrai fichier officiel).
# ---------------------------------------------------------------------------------------------------------------
CODES_STATUT = {"1": ("RS", "Rupture de stock"), "2": ("TA", "Tension d'approvisionnement"),
                "3": ("AC", "Arrêt de commercialisation"), "4": ("RD", "Remise à disposition")}


def type_dispo(chemin) -> str:
    """'web' = export du site ANSM (avec en-tête 'Titre', sans CIS) ; 'officiel' = CIS_CIP_Dispo_Spec de la BDPM."""
    chemin = Path(chemin)
    if chemin.suffix.lower() in (".xls", ".xlsx"):
        return "web"
    debut = chemin.read_bytes()[:400].decode("utf-8-sig", errors="replace")
    return "web" if "Titre" in debut.split("\n")[0] else "officiel"


def _titre_depuis_url(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\s+", " ", slug.replace("-", " ")).strip().capitalize() or url


def nettoyer_dispo_officiel(chemin, cis_connus=None, date_import=None):
    """Retourne (alertes, liens, rejets, anomalies) dans les mêmes formes que nettoyer_ansm + rapprocher."""
    from clean_bdpm import lire_bdpm, COLS_DISPO, _date           # import local : évite la dépendance circulaire
    df = lire_bdpm(chemin, COLS_DISPO)
    anomalies = {"lignes_lues": len(df), "lignes_realignees": len(df.attrs["lignes_realignees"])}
    df["Code_CIS"] = df["Code_CIS"].str.zfill(8)
    df["Code_CIP13"] = df["Code_CIP13"].fillna("")
    for c, n in (("Date_debut", "Date_Debut"), ("Date_MAJ", "Date_MAJ_ANSM"), ("Date_remise_dispo", "Date_Fin_Prevue")):
        df[n] = _date(df[c])
        anomalies[f"{n}_illisibles"] = int((df[n].isna() & df[c].notna()).sum())
    df["Statut_Code"] = df["Code_statut"].map(lambda c: CODES_STATUT.get(c, (None, None))[0])
    df["Statut_Libelle"] = df["Code_statut"].map(lambda c: CODES_STATUT.get(c, (None, None))[1])
    anomalies["statuts_inconnus"] = int(df["Statut_Code"].isna().sum())
    ok = df.dropna(subset=["Statut_Code", "Date_Debut", "URL_Information", "Code_CIS"])
    rejets = df.loc[~df.index.isin(ok.index), ["Code_CIS", "Code_CIP13", "Code_statut", "URL_Information"]].assign(Raison="statut/date/URL manquant")
    df = ok.copy()
    # UNE ALERTE PAR LIGNE (fiche, CIS, CIP13) : le statut peut différer d'un CIS à l'autre d'une même fiche.
    df["Id_Alerte"] = (df["URL_Information"] + "|" + df["Code_CIS"] + "|" + df["Code_CIP13"]).map(_id_alerte)
    anomalies["doublons_exacts_supprimes"] = int(df["Id_Alerte"].duplicated().sum())
    df = df.sort_values("Date_MAJ_ANSM", na_position="first").drop_duplicates("Id_Alerte", keep="last")
    div = df.groupby("URL_Information")[["Statut_Code"]].nunique().max(axis=1)
    anomalies["fiches"] = int(df["URL_Information"].nunique())
    anomalies["fiches_a_statuts_differents_selon_cis"] = int((div > 1).sum())
    # le CIS inconnu de CIS_bdpm n'empêche PAS de garder l'alerte (sinon des fiches entières disparaîtraient) ;
    # seul le LIEN vers MEDICAMENT manque (clé étrangère) : le CIS reste dans Code_CIS_source et dans les rejets.
    connu = df["Code_CIS"].isin(cis_connus) if cis_connus is not None else pd.Series(True, index=df.index)
    anomalies["lignes_cis_absent_de_bdpm"] = int((~connu).sum())
    rejets = pd.concat([rejets, df.loc[~connu, ["Code_CIS", "Code_CIP13", "Code_statut", "URL_Information"]]
                        .assign(Raison="CIS absent de CIS_bdpm : alerte conservée, sans lien vers MEDICAMENT")])
    df["Titre"] = df["URL_Information"].map(_titre_depuis_url)
    df["Nom_produit"] = df["Titre"]
    df["Substances"] = None
    for c in ("Date_Creation", "Produit_sante", "Domaine_medical"):
        df[c] = None
    df["Code_CIS_source"] = df["Code_CIS"]
    df["Code_CIP13_source"] = df["Code_CIP13"].replace("", None)
    df["Date_Import"] = date_import or pd.Timestamp.today().strftime("%Y-%m-%d")
    alertes = df[["Id_Alerte", "Titre", "Nom_produit", "Substances", "Statut_Code", "Statut_Libelle", "Date_Creation",
                  "Date_MAJ_ANSM", "Date_Debut", "Date_Fin_Prevue", "Produit_sante", "Domaine_medical",
                  "URL_Information", "Code_CIS_source", "Code_CIP13_source", "Date_Import"]].reset_index(drop=True)
    liens = df.loc[connu, ["Id_Alerte", "Code_CIS", "Code_CIP13"]].assign(Score_confiance=1.0, Methode="officiel_CIS")
    return alertes, liens.reset_index(drop=True), rejets.reset_index(drop=True), anomalies
