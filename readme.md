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

Les fiches détaillées sont dans `Personas_complet.pdf`.

* **Cibles Primaires :**
  * **Patients chroniques et proches aidants (Hélène LAMBERT, 62 ans, Nantes ; Jean DUPONT, 58 ans, Montpellier) :** recherchent une information claire et rassurante sur leur traitement, avec une alternative officielle qu'ils peuvent imprimer ou montrer à leur pharmacien ou à leur médecin avant de se déplacer.
  * **Pharmaciens d'officine (Karim BENALI, 44 ans, Lyon ; Jordan CASSEMIRO, 45 ans, Nîmes) :** recherchent un outil de comptoir ultra-rapide (recherche par nom, code CIS ou CIP13) pour trouver une substitution légale immédiate.
* **Cibles Secondaires :**
  * **Médecins généralistes (Patricia MUSSET, 51 ans, Montpellier ; Sophie MARCHAND, 51 ans, Toulouse) :** vérification rapide en consultation pour éviter de prescrire un traitement indisponible, avec les alternatives du même groupe générique.
  * **Journalistes santé (Lisa POIRREAU, 29 ans, Paris) :** exploration de l'historique des ruptures et export de données sourcées (CSV, graphiques).
* **Anti-personas (hors cible) :**
  * **Revendeur en ligne (Mathieu GARNIER, 34 ans, Marseille) :** veut un export massif et automatisé des ruptures pour anticiper les pénuries et revendre plus cher.
  * **Délégué commercial pharmaceutique (Thomas LEROY, 38 ans, Paris) :** cherche de la veille commerciale, alors que la plateforme ne met aucune marque en avant.
  * **Chercheuse en pharmacologie (Sophie MARTIN, 36 ans, Toulouse) :** attend des données scientifiques détaillées (mécanismes d'action, études cliniques) que la plateforme ne propose pas.

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
