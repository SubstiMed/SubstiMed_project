# SubstiMed : La continuité de vos soins

> **Plateforme web de suivi des tensions d'approvisionnement et d'aide à la substitution médicamenteuse.**  
> *Projet universitaire : Cours de Gestion de Projet (2026)*

---

## Informations Générales

* **Nom du projet :** SubstiMed
* **Groupe :** `...`
* **Membres de l'équipe :**
  * ...

---

## Problématique et Proposition de Valeur

### Besoins et problèmes identifiés
Les ruptures de stock et tensions d'approvisionnement sur les médicaments essentiels se multiplient. 
* **Pour les patients :** Cela génère un parcours d'accès au soin stressant (multiplication des pharmacies visitées) et un risque réel de rupture de traitement.
* **Pour les professionnels de santé (médecins, pharmaciens) :** Le suivi des alertes de l'ANSM et la vérification des équivalences disponibles prennent un temps précieux au comptoir ou en consultation.

### Notre solution
**SubstiMed** est une application web centralisant en temps réel les données officielles de disponibilité et le référentiel des spécialités pharmaceutiques. Elle permet en une seule recherche :
1. De vérifier le statut d'approvisionnement national d'un médicament (Disponible, Tension d'approvisionnement, Rupture de stock, Arrêt de commercialisation, Remise à disposition).
2. D'identifier instantanément les alternatives disponibles (même groupe générique ou même substance active et dosage).
3. D'analyser les tendances de pénuries via un tableau de bord dédié.

---

## Usagers Cibles (Personas)

Les fiches détaillées sont disponibles dans `docs/personas/Personas_complet.pdf`.

* **Cibles Primaires :**
  * **Patients chroniques et proches aidants (Hélène LAMBERT, 62 ans ; Jean DUPONT, 58 ans) :** recherchent une information claire et rassurante sur leur traitement, avec une alternative officielle qu'ils peuvent imprimer ou montrer à leur pharmacien ou médecin.
  * **Pharmaciens d'officine (Karim BENALI, 44 ans ; Jordan CASSEMIRO, 45 ans) :** recherchent un outil de comptoir ultra-rapide (recherche par nom, code CIS ou CIP13) pour trouver une substitution légale immédiate.
* **Cibles Secondaires :**
  * **Médecins généralistes (Patricia MUSSET, 51 ans ; Sophie MARCHAND, 51 ans) :** vérification rapide en consultation pour éviter de prescrire un traitement indisponible.
  * **Journalistes santé (Lisa POIRREAU, 29 ans) :** exploration de l'historique des ruptures et export de données sourcées (CSV, graphiques).
* **Anti-personas (hors cible) :**
  * **Revendeur en ligne (Mathieu GARNIER, 34 ans) :** veut spéculer sur les pénuries.
  * **Délégué commercial (Thomas LEROY, 38 ans) :** recherche de la veille commerciale (la plateforme est neutre et ne valorise aucune marque).
  * **Chercheuse en pharmacologie (Sophie MARTIN, 36 ans) :** attend des détails pharmacodynamiques cliniques hors périmètre.

---

## Base de Données et Architecture des Données

Le projet repose sur le croisement de deux sources institutionnelles officielles en Open Data (fichiers tabulés, encodage Windows `cp1252`, sans en-tête) :

1. **BDPM (Base de Données Publique des Médicaments) :**
   * `CIS_bdpm.csv` : Référentiel national des spécialités pharmaceutiques (`Code_CIS` à 8 chiffres).
   * `CIS_CIP_bdpm.csv` : Présentations et boîtes physiques commercialisées (`Code_CIP13`, prix, taux de remboursement).
   * `CIS_COMPO_bdpm.csv` : Composition qualitative et quantitative (`Code_substance`, dosage, référence).
   * `CIS_GENER_bdpm.csv` : Groupes génériques officiels pour la substitution légale (`Identifiant_groupe_generique`, type princeps/générique).
2. **ANSM (Agence Nationale de Sécurité du Médicament) :**
   * `CIS_CIP_Dispo_Spec.txt` : Fichier officiel de suivi des ruptures et tensions (codes CIS, CIP13, codes statuts RS/TA/AC/RD, dates d'effet et liens vers les fiches officielles).

### Spécificités et corrections du modèle relationnel
* **Table `COMPOSITION` :** Le dosage est porté par le couple (Médicament $\times$ Substance) avec sa référence de prise (`Reference_dosage`, ex: *pour un comprimé*, *pour 100 ml*), et non dans la table `SUBSTANCE` isolée.
* **Table `MEDICAMENT_GROUPE` (Cardinalité réelle 0,N) :** Dans la BDPM, 57 médicaments appartiennent simultanément à plusieurs groupes génériques (complémentarité posologique). La table associative gère cette multiplicité et stocke le `Type_generique` (0 princeps, 1 générique).
* **Table associative `ALERTE_CIS` :** Fait le lien entre les fiches `RUPTURE_ANSM` et `MEDICAMENT`. Elle préserve l'intégrité en isolant les alertes portant sur des médicaments retirés de la BDPM depuis plus de 2 ans, et gère les ruptures ciblant des boîtes spécifiques (`Code_CIP13`).
* **Optimisation de recherche (`Denomination_norm`) :** Champ normalisé (minuscules, sans accents ni caractères spéciaux) avec index B-tree pour une autocomplétion instantanée dans la barre de recherche.

---

## Stack Technique & Prérequis

* **Environnement serveur web :** WAMP / Apache local
* **Base de données :** SQLite 3 (base prête à l'emploi `database/substimed.db` ; schéma standard compatible MySQL / PostgreSQL)
* **Back-end web :** PHP 8+ (Architecture PDO orientée requêtes préparées)
* **Front-end :** HTML5, CSS3, JavaScript moderne (`fetch` asynchrone pour l'autocomplétion)
* **Pipeline de données (ETL) :** Python 3.10+ (`pandas`)
* **Modélisation :** Mocodo (MCD / MLD)

---

## Pipeline ETL & Commandes Python

Les scripts de préparation et de contrôle des données sont situés dans le dossier `ETL/`.

```bash
# 1. Installation des dépendances Python
pip install -r ETL/requirements.txt

# 2. Exécution du chargement complet (ETL idempotent et transactionnel)
# Nettoie les données brutes de ETL/data/ et alimente database/substimed.db
python ETL/load_db.py

# 3. Lancer les 28 contrôles qualité automatiques (doublons, cohérence dates, EAN-13...)
# Génère les rapports détaillés dans ETL/logs/qualite_*.csv
python ETL/autres-scripts-utiles/quality_checks.py

# 4. Régénérer l'échantillon léger de 100 médicaments (avec cas de substitution et alertes)
# Génère data_sample/ et copie database/substimed_sample.db
python ETL/autres-scripts-utiles/make_sample.py
```

---

## Structure du Projet

```text
/SubstiMed_project                     # Racine du projet (dépôt Git)
├── README.md                          # Documentation générale et technique
├── .gitignore                         # Fichiers temporaires, caches Python, etc.
│
├── /database                          # Données et schémas relationnels
│   ├── schema.sql                     # Script DDL de création des tables et index
│   ├── substimed.db                   # Base de données complète prête à l'emploi (18 Mo)
│   ├── substimed_sample.db            # Échantillon de test léger (~100 médicaments)
│   └── Contenu_et_format_des_...pdf   # Spécification officielle du format BDPM
│
├── /docs                              # Dossier documentaire
│   ├── /conception                    # Sources de modélisation (MCD.mcd, MCD.svg, MCD_MOD.pdf)
│   └── /personas                      # Profils utilisateurs (Personas_complet.pdf)
│
├── /ETL                               # Pipeline d'ingestion et de nettoyage Python
│   ├── clean_bdpm.py                  # Normalisation des tables BDPM (CIS, CIP, COMPO, GENER)
│   ├── clean_ansm.py                  # Normalisation du flux de ruptures ANSM
│   ├── match_ansm.py                  # Module de repli (rapprochement flou pour exports web)
│   ├── load_db.py                     # Script principal d'import transactionnel (UPSERT)
│   ├── common.py                      # Constantes et utilitaires de normalisation
│   ├── requirements.txt               # Dépendances Python (pandas)
│   ├── /data                          # Fichiers sources d'origine (BDPM + ANSM)
│   ├── /logs                          # Fichiers de rejets et rapports de conformité
│   └── /autres-scripts-utiles         # Outils d'audit et d'échantillonnage
│       ├── quality_checks.py          # 28 contrôles qualité automatisés
│       ├── make_sample.py             # Extracteur d'échantillon cohérent
│       └── /data_sample               # Exports CSV de l'échantillon
│
└── /SubstiMed.app                     # Application web servie par Apache
    ├── index.html                     # Interface principale de recherche et alertes
    ├── /config
    │   └── bd.php                     # Connexion PDO à la base database/substimed.db
    ├── /assets
    │   ├── /css
    │   │   └── styles.css             # Feuilles de styles
    │   └── /js
    │       └── main.js                # Scripts frontend (autocomplétion, fetch API)
    ├── /api                           # Endpoints JSON (recherche, alternatives, stats)
    └── /includes                      # Éléments réutilisables (header, footer, fonctions)
```

---

## Guide de Démarrage Rapide pour l'Équipe

1. **Développement Web (Front / Back) :**
   * L'application web est prête à interroger la base SQLite complète [`database/substimed.db`](file:///C:/wamp64/www/SubstiMed_project/database/substimed.db) ou l'échantillon [`database/substimed_sample.db`](file:///C:/wamp64/www/SubstiMed_project/database/substimed_sample.db).
   * La configuration PDO dans `SubstiMed.app/config/bd.php` pointe directement vers `__DIR__ . '/../../database/substimed.db'`.
2. **Recherche de Médicament & Substitution :**
   * Pour l'autocomplétion, interrogez la colonne `Denomination_norm` de `MEDICAMENT`.
   * Pour vérifier la disponibilité : vérifier la présence du `Code_CIS` dans `ALERTE_CIS` / `RUPTURE_ANSM`.
   * Pour proposer un substitut : chercher les autres médicaments partageant le même `Identifiant_groupe_generique` dans `MEDICAMENT_GROUPE` qui ne sont pas en rupture.
