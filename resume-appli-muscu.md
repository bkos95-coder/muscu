# Mon programme muscu — résumé du projet

Application de suivi de musculation, HIIT, callisthénie, course et santé du dos, construite sur mesure pour Benjamin.

**Version actuelle : 1.27.0** — 8 novembre 2026

---

## 1. Contexte

| | |
|---|---|
| Profil | 49 ans · 1,85 m · ~80 kg |
| Matériel | Home gym : banc Corength, Rack 500, barre olympique, barre EZ, haltères |
| Contraintes médicales | Discopathie L4-L5 / L5-S1 · pincement C5-C6 · hallux rigidus opéré (pied droit) |
| Objectifs | Renforcement musculaire, HIIT, reprise de la course à pied, dénivelé dans les collines |

---

## 2. Installation et déploiement

- Application **mono-fichier** installée en **PWA** sur le téléphone (Honor Magic 6 Pro) : icône d'accueil, plein écran, **fonctionne hors réseau**.
- En ligne : **https://bkos95-coder.github.io/muscu/** (GitHub, dépôt `muscu`).
- **Mise à jour** : Claude publie directement chaque nouvelle version sur GitHub depuis la conversation (envoi groupé de `index.html` et `sw.js`, puis vérification de la publication et des fichiers en ligne). Sur le téléphone, il suffit de fermer et rouvrir l'appli : elle se recharge toute seule.
- **Jeton GitHub « Claude muscu »** : accès limité au seul dépôt `muscu` (contenu en lecture/écriture, Pages, métadonnées), **valable jusqu'au 31 mars 2027**. À recoller dans chaque nouvelle conversation ; à l'échéance, *Regenerate token* dans GitHub. Le jeton n'est stocké ni dans ce document ni en mémoire.
- **Sauvegarde** : automatique sur le serveur AGEOTERRA en fin de séance, plus export / import d'un fichier JSON.

---

## 3. Les fonctions, par thème

### 📅 Semaine — le programme

- Composition automatique selon **1 à 5 séances par semaine**, **20 à 45 min**, style **Force / Équilibré / Cardio**.
- **Sécurité médicale intégrée** :
  - exclus : soulevé de terre, SDT jambes tendues, rowing barre penché, relevés inclinés ;
  - remplacés par : goblet squat, rowing 1 bras appuyé, curl-up McGill, pont fessier 1 jambe, développé haltères assis ;
  - un exercice « dos solide » et la planche présents dans chaque séance ;
  - signal stop : douleur qui irradie dans la jambe ou la fesse = arrêt.
- Suggestions de **progression des charges** (+2,5 kg quand une séance est bouclée deux fois).
- **Récap de la semaine** : séances, temps d'effort, calories.

### ⏱ Le déroulé de séance

- **3 modes** : Circuit · Série par série · Manuel.
- **Réglages au lancement** :
  - repos entre deux exercices (0 à 30 s) ;
  - repos entre deux tours ou deux séries (0 à 2 min) ;
  - mise en place avant un exercice chronométré (0 à 20 s) ;
  - décompte d'un chrono lancé à la main (1, 3 ou 5 s) ;
  - annonce vocale.
- **« C'est parti »** lance directement le premier exercice.
- **Page « À toi »** (exercices à répétitions) : nom, série, consigne, « Comment faire », charge, suite annoncée, grand bouton **✓ Fait · suivant** qui coche tout seul.
- **Écran du chrono** :
  - temps de séance en haut à gauche, **SÉRIE 2 / 5** en grand ;
  - exercice en cours en gros, chrono qui passe au rouge à la fin ;
  - **« Ensuite : … »** qui grossit et **clignote en rouge** dans les 5 dernières secondes ;
  - **⏸ Pause / ▶ Reprendre** (temps conservé même écran éteint), puis Fermer.
- **Sons** : bips de décompte, **coup de sifflet au départ** de chaque effort, double sifflet en fin de séance, **volume réglable** jusqu'à 150 %, bouton de test.
- **Écran maintenu allumé** pendant la séance.
- **Fin de séance** : séries cochées, durée totale, calories, ressenti (RPE, humeur, douleur, note).

### 🧩 Libre et modèles

- **Fiche de chaque exercice** : toucher un exercice déplie sa fiche (type, schéma, consigne, guide complet, ⚠ expliqué) avec un bouton « + Ajouter à ma sélection » ; le « + » à droite reste l'ajout direct.
- **Bibliothèque** :
  - musculation par groupe musculaire ;
  - **28 exercices de callisthénie** en 4 groupes 🤸 : Tirage, Poussée, Jambes, Gainage & statiques ;
  - **50+ exercices HIIT** en 4 groupes ⚡ ;
  - ⚠ sur les exercices qui sollicitent les **lombaires**, les **cervicales** ou le **pied droit**, avec l'explication.
- **« Ma sélection »** dans un panneau : ordre, séries, durées, répétitions, retrait.
- **« Tout régler d'un coup »** : séries, durée ou répétitions de tous les exercices en un appui.
- **Modèles** : 👁 aperçu (exercices, séries, **durée estimée**) · ▶ lancer · ✎ modifier · ⧉ dupliquer · ✕ supprimer.

### ⚡ HIIT

- 2 circuits par défaut sans saut, plus un **composeur de circuits**.
- **Réglages** : effort (20 s à 1 min), récup entre exercices, repos entre tours, mise en place ; durée réelle affichée avant de lancer.
- **Lecteur** : même écran que le chrono (TOUR 1 / 2 en grand, « Ensuite » qui clignote, temps de séance), sifflet au départ, bouton **Passer**, voix (« Prochain : … », « Fin du tour »).
- Arrêt en cours de route enregistrable (séance partielle).
- **Un circuit s'enregistre comme modèle** de la séance libre.

### 🏃 Fractionné course

- Échauffement en marche · course · marche · nombre de répétitions · retour au calme, avec durée totale affichée.
- **Sifflet et voix** à chaque changement (« Course, 1 minute », « Marche, 2 minutes »).
- **🔒 Verrou anti-touches** : écran noir lisible, appui long de 2 s pour déverrouiller.
- Enregistré comme **activité Course** (distance facultative à la fin).

### 🦴 Dos

- **Routine McGill de 12 min**.
- Suivi de la douleur et courbe d'évolution.

### 📊 Historique et suivi

- Fil de toutes les séances, HIIT et activités, avec **filtres** et **statistiques** par filtre : distance, allures, dénivelé, séries, tonnage, régularité, calories.
- **Corrections après coup** : charges, exercice (remplacement), séries, note, activités, pesées.
- **Poids** et **masse grasse** (en % ou en kg), masse maigre, évolution, **IMC** avec taille réglable, courbes.
- **Activités** : course, trail (dénivelé, allure d'effort), marche, vélo, padel (1h30 pré-rempli), natation, randonnée, étirements.
- **Calories estimées** (méthode MET, ±20 %) :
  - musculation ajustée au ressenti ;
  - HIIT : effort et récup comptés séparément ;
  - course, marche et vélo selon la vitesse réelle ;
  - trail et rando : coût de la montée ajouté ;
  - fractionné : course et marche séparées ;
  - repères à 80 kg : muscu 45 min ≈ 210 kcal · HIIT 17 min ≈ 150 kcal · course 5,2 km ≈ 440 kcal · trail 10,5 km / 420 m D+ ≈ 1 220 kcal · padel 1h30 ≈ 720 kcal.

---

## 4. Historique des versions

### Avant la 1.18

| Version | Contenu |
|---|---|
| 1.3 → 1.6 | Pompes par défaut dans le HIIT, palier 25 min, filtres et statistiques de l'historique |
| 1.7 | Sons refondus (bips renforcés, sifflets), anti-doublon planche, confirmation avant décochage |
| 1.8 → 1.10 | Bibliothèque HIIT étendue et ⚠, séance mixte muscu + HIIT, test des sons, réglage du volume |
| 1.11 → 1.12 | Corrections dans l'historique (séances, exercices, activités, pesées) |
| 1.13 → 1.15 | Cochage automatique, enchaînement automatique, déroulé unifié (Circuit / Série par série / Manuel) |
| 1.16 | Modèles modifiables et duplicables, « Ma sélection » ordonnée |
| 1.17 | Masse grasse (% ou kg), masse maigre |

### Depuis la 1.18

| Version | Contenu |
|---|---|
| 1.18.0 | IMC et taille réglable |
| 1.18.1 | Padel : 1h30 pré-rempli |
| 1.18.2 | « Ma sélection » dans un panneau (fin du chevauchement de la liste) |
| 1.18.3 | Carte du poids réorganisée, virgule française, unité du tonnage |
| 1.19.0 | Repos et mise en place réglables séparément |
| 1.20.0 | « Ensuite » pendant le chrono, page d'exercice enrichie, bouton « Fait · suivant » |
| 1.20.1 | « C'est parti » lance le premier exercice |
| 1.21.0 | Repos entre exercices / entre tours, 👁 aperçu des modèles avec durée estimée |
| 1.22.0 | Écran du chrono réorganisé, clignotement rouge, bouton Pause |
| 1.22.1 | Temps de séance sur le chrono et la page « À toi » |
| 1.22.2 | Audit complet : bouton « Lancer » toujours visible, formats de durée et de date, durée en fin de séance |
| 1.23.0 | 28 exercices de callisthénie, sifflet de départ |
| 1.24.0 | « Tout régler d'un coup » |
| 1.25.0 | Lecteur HIIT aligné, fractionné course avec verrou, circuit HIIT en modèle |
| 1.26.0 | Calories estimées partout |
| 1.27.0 | Fiche dépliable de chaque exercice dans le Libre, 108 apostrophes rétablies dans les guides — première version publiée directement depuis la conversation |

---

## 5. Qualité

- Chaque version est validée par des **tests automatisés** de la logique.
- Depuis la 1.18.2, chaque modification d'écran est aussi vérifiée **dans un vrai navigateur au format téléphone** : captures, débordements, clic sur chaque bouton, parcours complets (séance, HIIT, fractionné).
- **Audit complet** en 1.22.2 : 128 tests de logique, 73 boutons cliqués par taille d'écran, 11 écrans superposés contrôlés sur 3 tailles de téléphone.

---

## 6. Ce qui reste ouvert

### À tester en conditions réelles

- Le **fractionné téléphone verrouillé en poche** : vérifier que le sifflet et la voix sortent bien (sinon, régler l'économie de batterie de MagicOS pour l'application).
- Le **sifflet de départ** et le **nouvel écran du lecteur HIIT**.

### Proposé, non retenu pour l'instant

- **Réglages de déroulé propres à chaque type de séance** : aujourd'hui, les modèles HIIT et les séances de musculation partagent les mêmes repos.

### Idées notées

- Échauffement guidé avant la séance (prioritaire vu la discopathie)
- Récap PDF de la douleur pour le kiné
- Semaines allégées planifiées
- Rappels de régularité
- Import GPX Garmin

---

## 7. Mémo technique

| | |
|---|---|
| Fichiers à déployer | `index.html` · `sw.js` (les deux numéros de version doivent correspondre), envoyés en un seul commit sur la branche `main` |
| Publication | API GitHub (jeton à portée limitée), puis contrôle de la publication GitHub Pages et comparaison octet par octet des fichiers en ligne |
| Autres fichiers PWA | `manifest.webmanifest` · icônes 192, 512 et maskable |
| Stockage | `localStorage`, clé `monProgMuscu_v3` (migration automatique depuis la v2) |
| Minuteurs | Basés sur l'horloge réelle : ils restent justes après un gel d'écran Android |
| Écran allumé | Wake lock avec réacquisition automatique |
| Audio | Bus avec volume et limiteur ; voix française du téléphone |
