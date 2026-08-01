# Phase 11.8.10B-P1 — BrowseComp-Plus bounded clarification

Date: 2026-08-01

Methodology commit: `1b871eed97039a356b35e7eea5b505b057047388`

Canonical JSON SHA-256: `90336e77544b5ba7a3c4ddf21cf9f535377a57c19c5756941f67ee2304d00016`

Source-set SHA-256: `c071db37072290294abf6d417077e644bca94146b59ebef54a94fdd5ddefb56e`

## Observation principale

Le verrou d’ingénierie passe **18/18**, mais la décision de clarification reste
**`no_go`**. BrowseComp-Plus n’est pas admis : les droits des composants Web
et la fermeture immuable du juge/runtime restent incomplets. Le plafond de
recherche est entièrement consommé, avec cinq nouveaux documents et quinze
documents cumulés sur quinze.

Le résultat reproduit P0 à 16/16, vérifie quatorze autorités locales et se
reproduit octet pour octet. Il ne contient aucun payload, requête, réponse,
passage ni score benchmark. Les zéros opérationnels sont des attestations de
processus appuyées par un contrôle statique de capacité ; aucune
instrumentation réseau runtime complète n’est revendiquée.

## Failles

- **Droits — bloqué :** aucune des cinq nouvelles sources ne fournit la
  disposition autoritative, composant par composant, requise pour
  l’acquisition, le traitement local, le reporting agrégé et la
  non-redistribution du corpus Web tiers.
- **Juge/runtime — bloqué :** le runner amont nomme `Qwen/Qwen3-32B` et expose
  des valeurs par défaut, mais ne lie ni le modèle ni le tokenizer au SHA
  candidat. Les dépendances contiennent des plages de versions et une référence
  à une branche `main`, donc aucun environnement résolu unique n’est prouvé.
- **Prompt/algorithme — partiel :** le blob exact verrouille le prompt, le
  parser et l’agrégation dans le code source, pas la configuration effective
  d’une exécution après overrides et résolution du runtime.
- **Plafond atteint :** la page OpenAI non révisionnée n’a fermé aucun gate et
  le `no_go` ne dépend pas d’elle. Elle compte toutefois parmi les documents
  consultés ; aucune seizième source n’est autorisée.

## Points flous

- Il reste inconnu si l’autorité compétente peut fournir une disposition de
  droits suffisamment précise pour le périmètre EvidenceMesh prévu ; P1 ne
  rend aucun avis juridique.
- La révision exacte du modèle et du tokenizer, la configuration effective de
  génération, le lock runtime résolu et le contrat de scoring de la comparaison
  officielle ne sont pas établis ensemble dans une autorité immuable.
- Une clarification amont pourrait débloquer une future décision, mais elle ne
  vaut aujourd’hui ni permission d’acquisition, ni permission d’évaluation, ni
  preuve de comparabilité.

## 3 questions critiques

1. Une autorité amont peut-elle attester explicitement les droits couvrant
   acquisition, traitement local, reporting agrégé et non-redistribution de
   chaque composant tiers pertinent ?
2. Peut-elle fournir une fermeture reproductible unique du modèle, tokenizer,
   prompt effectif, génération, dépendances runtime, parser et scoring du track
   officiel à corpus fixe ?
3. Ces réponses seraient-elles assez immuables et précises pour fermer les deux
   gates sans nouvelle recherche ouverte, payload, proxy interne ou inférence
   juridique ?

## Action concrète recommandée

Préparer **un brouillon local et non envoyé de demande de clarification amont**,
limité aux deux questions bloquantes : disposition des droits des composants et
fermeture exacte du juge/runtime officiel.

Critères d’entrée : résultat P1 reproductible à 18/18 ; P0 reproduit à 16/16 ;
budget cumulé exactement à 15/15 avec zéro slot restant ; droits et
juge/runtime toujours bloqués ; critère d’arrêt P0 enregistré comme déclenché.

Critères d’arrêt : le brouillon nécessiterait une seizième source, un payload,
une conclusion juridique, un secret, un provider, un modèle, un juge, une
recherche, un score, un contact externe, une pièce jointe, une publication ou
une distribution.

Budget maximal : **0 requête externe, 0 retry, 0 publication**. L’envoi du
brouillon exige un GO explicite séparé. Acquisition, évaluation, Phase 11.9,
Phase 12, merge, release et claim de supériorité restent bloqués.
