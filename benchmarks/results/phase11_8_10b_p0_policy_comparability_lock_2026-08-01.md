# Phase 11.8.10B-P0 — Policy/Comparability Lock

Date: 2026-08-01

Methodology commit: `56989d4674f99184b11f72d18c503c320c65c868`

Canonical JSON SHA-256: `7e4062e9270eb8dc681783b0aac2ff031ea53310bbd9982c61fea0e458fc3798`

## Observation principale

Le verrou d’ingénierie passe **16/16**, mais la décision de qualité reste
**`no_go`**. Aucun des deux benchmarks n’est admissible aujourd’hui. Une
licence déclarée ne clôt pas les droits des composants tiers, et aucun score ne
peut être qualifié d’officiellement comparable tant que sa population et son
évaluateur ne sont pas entièrement immuables.

Le résultat est reproductible octet pour octet, lié à douze sources locales
allowlistées et aux cinq autorités exactes de la phase 11.8.10A. Il atteste dix
documents publics uniques consultés sur quinze autorisés, sans accès à un
payload benchmark. Les zéros opérationnels sont une attestation de processus
et un contrôle statique de capacité, pas une mesure réseau instrumentée.

## Failles

- **BRIGHT — bloqué :** droits tiers non ventilés, mapping exact entre le
  snapshot de 1 384 requêtes et la population/publication de 1 398 non prouvé,
  version et sémantique `pytrec_eval` non verrouillées.
- **BrowseComp-Plus — bloqué :** droits sur les pages Web et dérivés non
  ventilés ; juge Qwen, tokenizer, prompt, génération, runtime et contrat de
  scoring incomplets. La seule frontière défendable est le track officiel à
  corpus fixe BrowseComp-Plus, jamais BrowseComp open-Web.
- **Provenance externe :** sept documents GitHub ont un identifiant Git blob ;
  les trois cartes Hugging Face sont liées par révision et chemin seulement.
  P0 ne prétend pas avoir vérifié localement leur digest de contenu.

## Points flous

- La portée juridique exacte des licences déclarées sur les composants tiers
  reste à clarifier par une source primaire ; P0 ne rend pas d’avis juridique.
- La configuration officielle complète du juge BrowseComp-Plus n’est pas
  publiée de façon assez immuable dans les cinq documents consultés.
- Une seule suite autoritative pourra suffire plus tard, mais cela ne permet
  pas de sélectionner ou acquérir une suite avant sa propre clearance.

## 3 questions critiques

1. Une autorité primaire peut-elle fournir une disposition de droits couvrant
   l’usage local sans redistribution des composants BrowseComp-Plus ?
2. Existe-t-il une identité immuable complète pour le juge, le tokenizer, le
   prompt, la génération, les dépendances runtime et le scoring officiel ?
3. Ces preuves conservent-elles exactement la population et le track officiels
   BrowseComp-Plus à corpus fixe, sans les remplacer par un proxy interne ?

## Action concrète recommandée

Exécuter ensuite **une clarification metadata-only BrowseComp-Plus**, et elle
seule.

Critères d’entrée : P0 reproduit à 16/16 ; deux candidats toujours bloqués ;
BrowseComp-Plus seul candidat de clarification ; cinq documents uniques
restants ; cibles limitées aux droits composants et au verrou juge/runtime ;
GO séparé explicite.

Critères d’arrêt : plafond de quinze documents atteint ; besoin d’un payload,
secret, déchiffrement, provider, modèle, retrieval, juge ou scoring ; recours à
une référence mutable/secondaire ; affaiblissement vers un proxy interne ;
publication/redistribution nécessaire ; ou aucune suite avec tous ses gates
clos après la clarification.

Budget maximal : **5 documents publics uniques supplémentaires, 0 requête
payload, 0 requête provider/modèle, 0 retry**. Acquisition, évaluation,
publication, phase 11.9, phase 12, merge, release et claim de supériorité
restent interdits.
