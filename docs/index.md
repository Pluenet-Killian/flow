# CRE Interface

Bienvenue dans la documentation de **CRE Interface**, un système de surveillance de pipelines multibranches avec analyse de qualité de code.

## Présentation

CRE Interface permet de :

- **Surveiller les branches** d'un projet et leurs pipelines de build
- **Analyser la qualité du code** avec détection automatique des issues
- **Classifier les problèmes** par catégorie et sévérité
- **Identifier les bugs critiques** qui provoquent des crashs applicatifs
- **Suivre la résolution** des issues détectées

## Navigation rapide

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } **Concepts**

    ---

    Comprendre les notions fondamentales : issues, bugs, pipeline

    [:octicons-arrow-right-24: Lire les concepts](concepts/index.md)

-   :material-account:{ .lg .middle } **Guide utilisateur**

    ---

    Apprendre à utiliser l'interface au quotidien

    [:octicons-arrow-right-24: Guide utilisateur](user-guide/index.md)

-   :material-cog:{ .lg .middle } **Documentation technique**

    ---

    Architecture, composants et référence technique

    [:octicons-arrow-right-24: Doc technique](technical/architecture.md)

</div>

## Concepts clés

### Issues et BUGs

Le système distingue deux notions importantes :

| Concept | Description |
|---------|-------------|
| **Issue** | Tout problème de qualité de code détecté (sécurité, fiabilité, maintenabilité) |
| **BUG** | Étiquette supplémentaire sur une issue indiquant qu'elle provoque un crash |

!!! info "Point important"
    Une issue peut avoir l'étiquette **BUG** en plus de sa catégorie et sévérité.
    Voir [Étiquette BUG](concepts/bug-definition.md) pour comprendre la distinction.

### Pipeline

Chaque commit déclenche une pipeline composée de 3 étapes :

1. **Build I4Gen** - Compilation principale
2. **Build Compact** - Optimisation
3. **Issue Detector** - Analyse de qualité

## Démarrage rapide

```bash
# Installation des dépendances
npm install

# Lancement du serveur de développement
npm run dev
```

L'application sera disponible sur [http://localhost:3000](http://localhost:3000).
