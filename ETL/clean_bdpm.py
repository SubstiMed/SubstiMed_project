"""Nettoyage des fichiers BDPM (texte tabulé, SANS en-tête, encodage Windows cp1252). Clé de jointure : Code_CIS (8 chiffres).
Les fonctions renvoient des DataFrames propres + un dict d'anomalies (les DataFrames d'orphelins sont sous des clés '_...')."""
import pandas as pd
from common import ENCODAGE_BDPM, SEP_BDPM, norm

COLS_CIS = ["Code_CIS", "Denomination_medicament", "Forme_pharmaceutique", "Voies_administration",
            "Statut_AMM", "Type_procedure", "Etat_commercialisation", "Date_AMM", "Statut_BDM",
            "Numero_autorisation_europeenne", "Titulaire", "Surveillance_renforcee"]
COLS_CIP = ["Code_CIS", "Code_CIP7", "Libelle_presentation", "Statut_presentation", "Etat_commercialisation",
            "Date_declaration", "Code_CIP13", "Agrement_collectivites", "Taux_remboursement",
            "Prix_sans_honoraires", "Prix_avec_honoraires", "Honoraires", "Indications_remboursement"]
COLS_COMPO = ["Code_CIS", "Designation_element", "Code_substance", "Denomination_substance",
              "Dosage_substance", "Reference_dosage", "Nature", "Numero_liaison"]
COLS_GENER = ["Identifiant_groupe_generique", "Libelle_groupe_generique", "Code_CIS", "Type_generique", "Numero_tri"]
COLS_DISPO = ["Code_CIS", "Code_CIP13", "Code_statut", "Libelle_statut", "Date_debut", "Date_MAJ",
              "Date_remise_dispo", "URL_Information"]


def lire_bdpm(chemin, colonnes):
    """Lecture robuste : cp1252, tabulations, sans en-tête.
    - un éventuel tab final (COMPO, GENER) est ignoré ;
    - une ligne avec des tabs en trop (cas réel : 3 lignes COMPO d'homéopathie, 2 lignes GENER) est réalignée en
      retirant les champs vides excédentaires, et signalée dans df.attrs['lignes_realignees'] ;
    - jamais de ligne perdue silencieusement (pandas sautait ces lignes)."""
    n = len(colonnes)
    texte = open(chemin, "rb").read().decode(ENCODAGE_BDPM, errors="replace")
    lignes = [l for l in texte.replace("\r\n", "\n").replace("\r", "\n").split("\n") if l.strip()]
    rows, realignees = [], []
    for no, l in enumerate(lignes, 1):
        f = l.split(SEP_BDPM)
        while len(f) > n and f[-1] == "":
            f.pop()
        if len(f) > n:
            avant = len(f)
            while len(f) > n and "" in f[1:]:
                f.pop(f.index("", 1))
            realignees.append((no, avant))
            f = f[:n]
        f += [""] * (n - len(f))
        rows.append(f)
    df = pd.DataFrame(rows, columns=colonnes)
    for c in df.columns:
        df[c] = df[c].str.replace("\u00a0", " ", regex=False).str.strip().replace("", None)
    df.attrs["lignes_realignees"] = realignees
    df.attrs["caracteres_illisibles"] = texte.count("\ufffd")
    return df


def _date(s):
    return pd.to_datetime(s, format="%d/%m/%Y", errors="coerce").dt.strftime("%Y-%m-%d")


def _decimal(s):
    return pd.to_numeric(s.str.replace(" ", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")


def _base(df):
    return {"lignes_lues": len(df), "lignes_realignees": len(df.attrs["lignes_realignees"]),
            "caracteres_illisibles": df.attrs["caracteres_illisibles"]}


def nettoyer_cis(chemin):
    df = lire_bdpm(chemin, COLS_CIS)
    anomalies = _base(df)
    df["Code_CIS"] = df["Code_CIS"].str.zfill(8)
    anomalies["cis_invalides"] = int((~df["Code_CIS"].str.fullmatch(r"\d{8}", na=False)).sum())
    df = df[df["Code_CIS"].str.fullmatch(r"\d{8}", na=False)]
    anomalies["cis_doublons_supprimes"] = int(df["Code_CIS"].duplicated().sum())
    df = df.drop_duplicates("Code_CIS", keep="last")
    df["Date_AMM"] = _date(df["Date_AMM"])
    df["Titulaire"] = df["Titulaire"].str.replace(r"\s*;\s*", " ; ", regex=True)
    df["Surveillance_renforcee"] = df["Surveillance_renforcee"].str.capitalize()
    df["Denomination_norm"] = df["Denomination_medicament"].map(norm)
    return df[["Code_CIS", "Denomination_medicament", "Denomination_norm", "Forme_pharmaceutique", "Voies_administration",
               "Statut_AMM", "Etat_commercialisation", "Date_AMM", "Statut_BDM", "Titulaire", "Surveillance_renforcee"]], anomalies


def nettoyer_cip(chemin, cis_connus=None):
    df = lire_bdpm(chemin, COLS_CIP)
    anomalies = _base(df)
    df["Code_CIS"] = df["Code_CIS"].str.zfill(8)
    df["Date_declaration"] = _date(df["Date_declaration"])
    for c in ("Prix_sans_honoraires", "Prix_avec_honoraires", "Honoraires"):
        df[c] = _decimal(df[c])
    anomalies["cip13_invalides"] = int((~df["Code_CIP13"].str.fullmatch(r"\d{13}", na=False)).sum())
    df = df[df["Code_CIP13"].str.fullmatch(r"\d{13}", na=False)]
    anomalies["cip13_doublons_supprimes"] = int(df["Code_CIP13"].duplicated().sum())
    df = df.drop_duplicates("Code_CIP13", keep="last")
    if cis_connus is not None:                       # FK PRESENTATION -> MEDICAMENT
        orph = ~df["Code_CIS"].isin(cis_connus)
        anomalies["presentations_cis_inconnu_ecartees"] = int(orph.sum())
        anomalies["_orphelins"] = df[orph]
        df = df[~orph]
    return df[["Code_CIP13", "Code_CIS", "Code_CIP7", "Libelle_presentation", "Statut_presentation",
               "Etat_commercialisation", "Date_declaration", "Agrement_collectivites", "Taux_remboursement",
               "Prix_sans_honoraires", "Prix_avec_honoraires", "Honoraires"]], anomalies


def nettoyer_compo(chemin, cis_connus=None):
    """CIS_COMPO_bdpm : 1 ligne = 1 substance (SA) ou fraction thérapeutique (FT) d'un élément d'un médicament.
    Retourne (SUBSTANCE, COMPOSITION, anomalies). Les champs de la clé d'unicité sont '' (jamais NULL) pour que
    le rejeu ne crée pas de doublons. Un Code_substance a parfois plusieurs graphies : on garde la plus fréquente."""
    df = lire_bdpm(chemin, COLS_COMPO)
    anomalies = _base(df)
    df["Code_CIS"] = df["Code_CIS"].str.zfill(8)
    if cis_connus is not None:
        orph = ~df["Code_CIS"].isin(cis_connus)
        anomalies["compo_cis_inconnu_ecartees"] = int(orph.sum())
        anomalies["_orphelins"] = df[orph]
        df = df[~orph]
    graphies = (df.groupby("Code_substance")["Denomination_substance"]
                  .agg(lambda s: sorted(s.value_counts().items(), key=lambda kv: (-kv[1], kv[0]))[0][0]))
    anomalies["substances_a_graphies_multiples"] = int((df.groupby("Code_substance")["Denomination_substance"].nunique() > 1).sum())
    subst = graphies.rename("Denomination_substance").reset_index()
    cles = ["Code_CIS", "Designation_element", "Code_substance", "Dosage_substance", "Reference_dosage", "Nature", "Numero_liaison"]
    compo = df[cles].fillna("")
    anomalies["compo_doublons_supprimes"] = int(compo.duplicated().sum())
    return subst, compo.drop_duplicates(), anomalies


def nettoyer_gener(chemin, cis_connus=None):
    """CIS_GENER_bdpm. ATTENTION : un CIS peut appartenir à PLUSIEURS groupes (complémentarité posologique) ;
    la clé est (CIS, groupe). Types : 0 princeps, 1 générique, 2 complémentarité posologique, 4 générique substituable.
    Le fichier cite aussi des CIS absents de CIS_bdpm (AMM anciennes) : écartés et comptés."""
    df = lire_bdpm(chemin, COLS_GENER)
    anomalies = _base(df)
    df["Code_CIS"] = df["Code_CIS"].str.zfill(8)
    df["Type_generique"] = pd.to_numeric(df["Type_generique"], errors="coerce").astype("Int64")
    if cis_connus is not None:
        orph = ~df["Code_CIS"].isin(cis_connus)
        anomalies["gener_cis_inconnu_ecartes"] = int(orph.sum())
        anomalies["_orphelins"] = df[orph]
        df = df[~orph]
    liens = df[["Code_CIS", "Identifiant_groupe_generique", "Type_generique"]].drop_duplicates(["Code_CIS", "Identifiant_groupe_generique"])
    anomalies["cis_dans_plusieurs_groupes"] = int(liens["Code_CIS"].duplicated().sum())
    groupes = (df[df["Identifiant_groupe_generique"].isin(liens["Identifiant_groupe_generique"])]
               [["Identifiant_groupe_generique", "Libelle_groupe_generique"]].drop_duplicates("Identifiant_groupe_generique"))
    return groupes, liens, anomalies
