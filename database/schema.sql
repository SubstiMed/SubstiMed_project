-- SubstiMed : schéma d'après le MCD (SQL standard, testé sous SQLite 3.35+).
-- PostgreSQL : remplacer "INTEGER PRIMARY KEY AUTOINCREMENT" par "GENERATED ALWAYS AS IDENTITY"
-- et "COLLATE NOCASE" par un index sur lower(...) ou l'extension pg_trgm.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS MEDICAMENT (
    Code_CIS                 CHAR(8)      PRIMARY KEY,
    Denomination_medicament  VARCHAR(400) NOT NULL,
    Denomination_norm        VARCHAR(400) NOT NULL,   -- minuscules, sans accents : pour la barre de recherche
    Forme_pharmaceutique     VARCHAR(200),
    Voies_administration     VARCHAR(200),
    Statut_AMM               VARCHAR(50),
    Etat_commercialisation   VARCHAR(50),
    Date_AMM                 DATE,
    Statut_BDM               VARCHAR(30),             -- 'Alerte' / 'Warning disponibilité' (signal propre à la BDPM)
    Titulaire                VARCHAR(400),
    Surveillance_renforcee   CHAR(3)
);

CREATE TABLE IF NOT EXISTS PRESENTATION (
    Code_CIP13               CHAR(13)     PRIMARY KEY,
    Code_CIS                 CHAR(8)      NOT NULL REFERENCES MEDICAMENT(Code_CIS),
    Code_CIP7                CHAR(7),
    Libelle_presentation     VARCHAR(400),
    Statut_presentation      VARCHAR(50),
    Etat_commercialisation   VARCHAR(120),
    Date_declaration         DATE,
    Agrement_collectivites   CHAR(3),
    Taux_remboursement       VARCHAR(20),
    Prix_sans_honoraires     DECIMAL(10,2),
    Prix_avec_honoraires     DECIMAL(10,2),
    Honoraires               DECIMAL(10,2)
);

CREATE TABLE IF NOT EXISTS SUBSTANCE (
    Code_substance           VARCHAR(10)  PRIMARY KEY,
    Denomination_substance   VARCHAR(300) NOT NULL
);

-- Association MEDICAMENT 1,N -- 0,N SUBSTANCE ("Est composé de"). Le dosage dépend du couple (médicament, substance) :
-- il est donc ici et non dans SUBSTANCE. Champs de la clé d'unicité jamais NULL ('' si absent) -> rejeu sans doublons.
CREATE TABLE IF NOT EXISTS COMPOSITION (
    Id_composition           INTEGER PRIMARY KEY AUTOINCREMENT,
    Code_CIS                 CHAR(8)      NOT NULL REFERENCES MEDICAMENT(Code_CIS),
    Designation_element      VARCHAR(200) NOT NULL DEFAULT '',   -- ex. "comprimé" (un médicament peut avoir plusieurs éléments)
    Code_substance           VARCHAR(10)  NOT NULL REFERENCES SUBSTANCE(Code_substance),
    Dosage_substance         VARCHAR(100) NOT NULL DEFAULT '',
    Reference_dosage         VARCHAR(100) NOT NULL DEFAULT '',   -- ex. "un comprimé", "100 ml" : indispensable pour comparer deux dosages
    Nature                   VARCHAR(4)   NOT NULL DEFAULT '',   -- SA = substance active ; FT = fraction thérapeutique (la doc écrit "ST")
    Numero_liaison           VARCHAR(10)  NOT NULL DEFAULT '',
    UNIQUE (Code_CIS, Designation_element, Code_substance, Dosage_substance, Reference_dosage, Nature, Numero_liaison)
);

CREATE TABLE IF NOT EXISTS GROUPE_GENERIQUE (
    Identifiant_groupe_generique VARCHAR(10) PRIMARY KEY,
    Libelle_groupe_generique     VARCHAR(500) NOT NULL
);

-- "Substitue" : ATTENTION, le MCD dit 0,1 mais les données montrent qu'un CIS peut être dans PLUSIEURS groupes
-- (57 CIS dans les données actuelles : complémentarité posologique) -> cardinalité réelle 0,N ; clé = (CIS, groupe).
CREATE TABLE IF NOT EXISTS MEDICAMENT_GROUPE (
    Code_CIS                     CHAR(8)     NOT NULL REFERENCES MEDICAMENT(Code_CIS),
    Identifiant_groupe_generique VARCHAR(10) NOT NULL REFERENCES GROUPE_GENERIQUE(Identifiant_groupe_generique),
    Type_generique               SMALLINT,               -- 0 princeps, 1 générique, 2 complémentarité posologique, 4 générique substituable
    PRIMARY KEY (Code_CIS, Identifiant_groupe_generique)
);

-- RUPTURE_ANSM = ÉTAT COURANT d'une alerte. Fichier officiel : 1 ligne par (fiche ANSM, CIS, CIP13) car le statut peut
-- différer d'un CIS à l'autre d'une même fiche (cf. MCD : « Subit Alerte » 1,1). Export web : 1 ligne par fiche.
CREATE TABLE IF NOT EXISTS RUPTURE_ANSM (
    Id_Alerte                VARCHAR(20)  PRIMARY KEY,   -- "ANSM-" + sha1(URL[|CIS|CIP13])[:12] : stable d'un import à l'autre
    Titre                    VARCHAR(600) NOT NULL,      -- export web : titre ANSM ; fichier officiel : déduit de l'URL
    Statut_Code              VARCHAR(4)   NOT NULL CHECK (Statut_Code IN ('RS','TA','RD','AC')),
    Statut_Libelle           VARCHAR(60)  NOT NULL,
    Date_Creation            DATE,
    Date_MAJ_ANSM            DATE,
    Date_Debut               DATE         NOT NULL,
    Date_Fin_Prevue          DATE,                      -- "Date de remise à disposition" du fichier ANSM
    Produit_sante            VARCHAR(40),
    Domaine_medical          VARCHAR(200),
    URL_Information          VARCHAR(600) NOT NULL,      -- plusieurs lignes peuvent partager la même fiche ANSM
    Code_CIS_source          CHAR(8),                    -- CIS tel que fourni par le fichier source (peut être absent de MEDICAMENT : pas de FK)
    Code_CIP13_source        CHAR(13),
    Date_Premier_Import      DATE         NOT NULL,
    Date_Dernier_Import      DATE         NOT NULL
);

-- "Subit Alerte". Une fiche ANSM peut viser plusieurs CIS (et plusieurs CIP13) -> table d'association.
--  * fichier officiel CIS_CIP_Dispo_Spec (CIS fournis)  : Methode = 'officiel_CIS', Score = 1.0
--  * export web ANSM (pas de CIS)                       : rapprochement par nom (match_ansm.py), Score < 1
-- Code_CIP13 = '' quand TOUTES les présentations du CIS sont concernées (comme dans le fichier officiel).
CREATE TABLE IF NOT EXISTS ALERTE_CIS (
    Id_Alerte                VARCHAR(20)  NOT NULL REFERENCES RUPTURE_ANSM(Id_Alerte),
    Code_CIS                 CHAR(8)      NOT NULL REFERENCES MEDICAMENT(Code_CIS),
    Code_CIP13               CHAR(13)     NOT NULL DEFAULT '',
    Score_confiance          DECIMAL(3,2) NOT NULL,
    Methode                  VARCHAR(40)  NOT NULL,
    PRIMARY KEY (Id_Alerte, Code_CIS, Code_CIP13)
);

-- HISTORIQUE : append-only. Une ligne est ajoutée à chaque changement de statut/dates constaté à un import.
CREATE TABLE IF NOT EXISTS RUPTURE_HISTORIQUE (
    Id_Historique            INTEGER PRIMARY KEY AUTOINCREMENT,
    Id_Alerte                VARCHAR(20)  NOT NULL REFERENCES RUPTURE_ANSM(Id_Alerte),
    Statut_Code              VARCHAR(4)   NOT NULL,
    Date_Debut               DATE         NOT NULL,
    Date_Fin_Prevue          DATE,
    Date_MAJ_ANSM            DATE,
    Date_Import              DATE         NOT NULL,
    Empreinte                CHAR(40)     NOT NULL,
    UNIQUE (Id_Alerte, Empreinte)
);

CREATE TABLE IF NOT EXISTS IMPORT_LOG (
    Id_Import                INTEGER PRIMARY KEY AUTOINCREMENT,
    Date_Import              TIMESTAMP    NOT NULL,
    Source                   VARCHAR(120) NOT NULL,
    Sha256                   CHAR(64)     NOT NULL,
    Nb_lignes                INTEGER,
    Nb_nouvelles             INTEGER,
    Nb_modifiees             INTEGER
);

-- INDEX demandés : Code_CIS, Code_CIP13, dénomination (+ jointures et tableau de bord)
CREATE INDEX IF NOT EXISTS idx_med_denomination      ON MEDICAMENT (Denomination_medicament COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_med_denomination_norm ON MEDICAMENT (Denomination_norm);
CREATE INDEX IF NOT EXISTS idx_presentation_cis      ON PRESENTATION (Code_CIS);
CREATE INDEX IF NOT EXISTS idx_compo_cis             ON COMPOSITION (Code_CIS);
CREATE INDEX IF NOT EXISTS idx_compo_substance       ON COMPOSITION (Code_substance);
CREATE INDEX IF NOT EXISTS idx_medgroupe_groupe      ON MEDICAMENT_GROUPE (Identifiant_groupe_generique);
CREATE INDEX IF NOT EXISTS idx_alerte_cis_cis        ON ALERTE_CIS (Code_CIS);
CREATE INDEX IF NOT EXISTS idx_rupture_statut_debut  ON RUPTURE_ANSM (Statut_Code, Date_Debut);
CREATE INDEX IF NOT EXISTS idx_rupture_url          ON RUPTURE_ANSM (URL_Information);
CREATE INDEX IF NOT EXISTS idx_rupture_cis_source   ON RUPTURE_ANSM (Code_CIS_source);
CREATE INDEX IF NOT EXISTS idx_rupture_domaine       ON RUPTURE_ANSM (Domaine_medical);
CREATE INDEX IF NOT EXISTS idx_histo_alerte_date     ON RUPTURE_HISTORIQUE (Id_Alerte, Date_Import);
-- Code_CIS (MEDICAMENT) et Code_CIP13 (PRESENTATION) sont déjà indexés via leur PRIMARY KEY.
