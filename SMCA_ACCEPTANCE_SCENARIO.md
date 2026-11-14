# Scénario de recette fonctionnelle SMCA

Ce scénario valide le processus complet : contexte → BIA → identification → cartographie → contrôle → traitement → risque résiduel → surveillance.

## 1. Périmètre

1. Se connecter comme administrateur.
2. Ouvrir **Parcours SMCA**.
3. Définir le périmètre, les objectifs, les parties intéressées, le seuil d’acceptation et la date de revue.
4. Vérifier que l’étape « Contexte et périmètre » devient complète.

## 2. BIA et dépendances

1. Ouvrir **BIA & dépendances**.
2. Évaluer une activité avec ses quatre impacts, MTPD, RTO et RPO.
3. Vérifier que `RTO ≤ MTPD` et `RPO ≤ MTPD` sont contrôlés.
4. Relier l’activité à une autre activité dans la cartographie des dépendances.

## 3. Risque et cartographie

1. Ouvrir **Registre des risques** et créer un risque lié à l’activité.
2. Renseigner menace, causes, vulnérabilités, conséquences, mesures existantes et date de revue.
3. Vérifier le calcul en direct du score.
4. Ouvrir **Cartographie 5×5** et vérifier la position du risque.
5. Comparer les modes inhérent, résiduel et courant.

## 4. Contrôles et preuves

1. Depuis la fiche risque, ajouter un contrôle avec responsable, efficacité et prochaine date de test.
2. Ajouter une pièce justificative.
3. Vérifier l’alerte lorsque la date de test est échue.

## 5. Traitement

1. Comme Risk Manager, proposer un plan et des actions mesurables.
2. Comme administrateur ou responsable SMCA distinct, approuver le plan avec commentaire.
3. Démarrer le plan puis terminer chaque action avec un résultat.
4. Clôturer et saisir la probabilité et l’impact résiduels.
5. Vérifier le déplacement du risque dans la matrice résiduelle.

## 6. KRI et incident

1. Ajouter un KRI depuis la fiche risque et saisir des seuils d’alerte et critique.
2. Faire franchir le seuil critique et vérifier le tableau de bord.
3. Enregistrer un incident lié au risque, puis documenter son impact et les enseignements.

## 7. Gouvernance et sécurité

1. Vérifier qu’un Department Manager ne voit que son département.
2. Vérifier qu’un Auditor ne peut rien modifier.
3. Exporter PDF et Excel et contrôler le périmètre des données.
4. Consulter le journal d’audit.
5. Créer un utilisateur et vérifier le changement obligatoire du mot de passe temporaire.

