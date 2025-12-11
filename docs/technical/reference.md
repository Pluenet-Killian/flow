# Référence technique

Cette page regroupe les tableaux de référence pour le développement.

## Catégories d'issues

| Catégorie | Icône | Classe couleur | Description |
|-----------|-------|----------------|-------------|
| Security | `Shield` | `text-red-600` | Vulnérabilités de sécurité |
| Reliability | `AlertTriangle` | `text-orange-600` | Problèmes de fiabilité |
| Maintainability | `Wrench` | `text-blue-600` | Problèmes de maintenabilité |

```typescript
type Category = 'Security' | 'Reliability' | 'Maintainability';
```

## Sévérités

| Sévérité | Priorité | Classes Tailwind | Hex approx. |
|----------|:--------:|------------------|-------------|
| Blocker | 1 | `bg-red-600 text-white` | #dc2626 |
| Critical | 2 | `bg-red-500 text-white` | #ef4444 |
| Major | 3 | `bg-orange-500 text-white` | #f97316 |
| Medium | 4 | `bg-yellow-500 text-white` | #eab308 |
| Minor | 5 | `bg-blue-500 text-white` | #3b82f6 |
| Info | 6 | `bg-gray-500 text-white` | #6b7280 |

```typescript
type Severity = 'Blocker' | 'Critical' | 'Major' | 'Medium' | 'Minor' | 'Info';
```

## Statuts des issues

| Statut | Icône | Bordure | Fond | Label FR |
|--------|-------|---------|------|----------|
| `pending` | `Circle` | `#d1d5db` | `#ffffff` | Non traité |
| `in-progress` | `Clock` | `#f59e0b` | `#fef3c7` | En cours |
| `done` | `CheckCircle2` | `#10b981` | `#d1fae5` | Terminé |

```typescript
type IssueStatus = 'pending' | 'in-progress' | 'done';
```

### Cycle de transition

```
pending → in-progress → done → pending
```

## Statuts des commits

| Statut | Icône | Couleur | Condition |
|--------|-------|---------|-----------|
| `success` | `CheckCircle2` | Vert | Pipeline OK + tous bugs reconnus |
| `failure` | `XCircle` | Rouge | Pipeline KO ou bugs non reconnus |
| `running` | `Loader` | Orange | Pipeline en cours |

```typescript
type CommitStatus = 'success' | 'failure' | 'running';
```

## Étiquette BUG

| Aspect | Valeur |
|--------|--------|
| **Type** | Booléen (`isBug: boolean`) |
| **Couleur badge** | `bg-purple-100 text-purple-700` |
| **Couleur checkbox** | `text-purple-600 border-purple-300` |
| **Couleur fond** | `bg-purple-50 border-purple-200` |
| **Impact** | Bloque le commit si non reconnu |

!!! warning "Rappel"
    BUG n'est pas une catégorie. C'est une étiquette supplémentaire sur une issue existante.

## Étapes de pipeline

| Étape | ID | Description |
|-------|-----|-------------|
| Build I4Gen | `build-i4gen` | Compilation principale |
| Build Compact | `build-compact` | Optimisation |
| Issue Detector | `issue-detector` | Analyse de qualité |

```typescript
interface PipelineNode {
  id: string;
  name: string;
  status: 'success' | 'failure';
  output: string;  // Markdown
}
```

## Types d'artifacts

| Type | Extension | Description |
|------|-----------|-------------|
| JAR | `.jar` | Archive Java |
| LOG | `.txt` | Logs de build |
| XML | `.xml` | Rapports de tests |

```typescript
interface Artifact {
  id: string;
  name: string;
  type: string;
  size: string;
}
```

## Variables CSS du thème

### Mode clair

| Variable | Valeur | Usage |
|----------|--------|-------|
| `--background` | `#ffffff` | Fond de page |
| `--foreground` | `oklch(0.145 0 0)` | Texte principal |
| `--primary` | `#030213` | Couleur principale |
| `--destructive` | `#d4183d` | Actions destructives |
| `--muted` | `#ececf0` | Éléments atténués |
| `--border` | `rgba(0,0,0,0.1)` | Bordures |
| `--radius` | `0.625rem` | Arrondi des coins |

### Mode sombre

| Variable | Valeur |
|----------|--------|
| `--background` | `oklch(0.145 0 0)` |
| `--foreground` | `oklch(0.985 0 0)` |
| `--primary` | `oklch(0.985 0 0)` |
| `--border` | `oklch(0.269 0 0)` |

## Icônes Lucide React

| Icône | Import | Usage |
|-------|--------|-------|
| `Shield` | `lucide-react` | Catégorie Security |
| `AlertTriangle` | `lucide-react` | Catégorie Reliability |
| `Wrench` | `lucide-react` | Catégorie Maintainability |
| `CheckCircle2` | `lucide-react` | Succès, Terminé |
| `XCircle` | `lucide-react` | Échec |
| `Clock` | `lucide-react` | En cours |
| `Circle` | `lucide-react` | Pending |
| `Settings` | `lucide-react` | Configuration |
| `ArrowLeft` | `lucide-react` | Retour |
| `Package` | `lucide-react` | Artifacts |
| `GitCommit` | `lucide-react` | Commits |

## Dépendances principales

| Package | Version | Usage |
|---------|---------|-------|
| react | ^18.3.1 | Framework UI |
| react-dom | ^18.3.1 | Rendu DOM |
| lucide-react | ^0.487.0 | Icônes |
| @radix-ui/react-* | ^1.x | Primitives UI |
| class-variance-authority | ^0.7.1 | Variantes CSS |
| tailwind-merge | * | Fusion classes |
| react-markdown | * | Rendu Markdown |
| react-syntax-highlighter | * | Coloration code |
| mermaid | * | Diagrammes |
| recharts | ^2.15.2 | Graphiques |

## Scripts npm

| Commande | Description |
|----------|-------------|
| `npm install` | Installation des dépendances |
| `npm run dev` | Serveur de développement (port 3000) |
| `npm run build` | Build de production (→ /build) |

## Voir aussi

- [Architecture](architecture.md) - Vue d'ensemble technique
- [Composants](components.md) - Description des composants
- [Système d'issues](../concepts/issues.md) - Documentation conceptuelle
