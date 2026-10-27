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
1. De vérifier le statut d'approvisionnement national d'un médicament.
2. D'identifier instantanément les alternatives disponibles (même groupe générique ou même substance active et dosage).
3. D'analyser les tendances de pénuries via un tableau de bord dédié.

---

## Usagers Cibles (Personas)

* **Cibles Primaires :**
  * **Patients chroniques & Aidants (ex: Thomas, 42 ans) :** Recherchent une information claire, rassurante (code couleur) et partageable avec leur médecin avant d'aller en pharmacie.
  * **Pharmaciens d'officine (ex: Sarah, 34 ans) :** Recherchent un outil de comptoir ultra-rapide (recherche par code CIS ou CIP13) pour trouver une substitution légale immédiate.
* **Cibles Secondaires :**
  * **Médecins généralistes (ex: Patricia, 51 ans) :** Vérification rapide en cours de consultation (12-15 min) pour éviter de prescrire un traitement indisponible.
  * **Journalistes santé & Chercheurs (ex: Lisa, 29 ans) :** Exploration de l'historique des ruptures et export de données (CSV/graphiques) sourcées.

---

## Base de Données et Sources (Architecture ETL)

Le projet repose sur le croisement de deux sources institutionnelles en Open Data :

1. **BDPM (Base de Données Publique des Médicaments) :**
   * `CIS_bdpm` : Table centrale des spécialités (Clé primaire : `Code_CIS` à 8 chiffres).
   * `CIS_CIP_bdpm` : Présentations et conditionnements physiques (`Code_CIP13`).
   * `CIS_COMPO_bdpm` : Composition qualitative et quantitative en substances actives (`Code_substance`, dosage).
   * `CIS_GENER_bdpm` : Groupes génériques pour le moteur de substitution (`Identifiant_groupe_generique`).
2. **ANSM (Agence Nationale de Sécurité du Médicament) :**
   * Fichier des déclarations de ruptures et tensions d'approvisionnement, relié au référentiel via le `Code_CIS`.

---

## Stack Technique & Prérequis

* **Environnement serveur :** WAMP / Apache (ou équivalent local)
* **Base de données :** MySQL / MariaDB
* **Back-end :** PHP 8+ (Architecture PDO orientée requêtes préparées)
* **Front-end :** HTML5, JavaScript (requêtes asynchrones `fetch` / AJAX pour l'autocomplétion)
* **Traitement de données / Conception :** Python (nettoyage CSV/TXT), Mocodo (MCD/MLD)

---

## Structure du Projet (MAJ régilière)

```
/SubstMed_app
|
├── /config
│   └── db.php                 # Connexion PDO sécurisée à la base MySQL
│
├── /api                       # Points d'entrée pour les requêtes
│
├── /includes                  # Composants réutilisables
│
├── /assets
│   ├── /css                   # Styles 
|   |   └── styles.css
│   └── /js                    # Scripts AJAX et configuration des graphiques
|       └── main.js
│
└── index.php                  # Vue : Recherche et dernières alertes

```
