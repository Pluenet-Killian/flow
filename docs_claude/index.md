# CRE - Code Review Engine

> Systeme d'analyse de code multi-agents avec base de donnees semantique AgentDB

---

## Qu'est-ce que CRE Flow ?

CRE Flow orchestre **8 agents specialises** pour produire des rapports de code review automatises. Il combine :

- **AgentDB** : Base de donnees semantique indexant le code source
- **Agents IA** : ANALYZER, SECURITY, REVIEWER, RISK, SYNTHESIS, SONAR, META-SYNTHESIS, WEB-SYNTHESIZER
- **Integration SonarCloud** : Enrichissement des issues SonarQube
- **API FastAPI** : Declenchement d'analyses via HTTP/WebSocket

---

## Architecture en 4 Phases

```
Phase 1 : ANALYZER + SECURITY + REVIEWER (parallele)
    |
Phase 2 : RISK -> SYNTHESIS + SONAR (parallele)
    |
Phase 3 : META-SYNTHESIS (fusion + deduplication)
    |
Phase 4 : WEB-SYNTHESIZER (JSON pour site web)
```

---

## Demarrage Rapide

### 1. Installation

```bash
# Dependances AgentDB
pip install -r .claude/agentdb/requirements.txt

# Dependances Backend
pip install fastapi websockets aiohttp pydantic python-dotenv
```

### 2. Configuration

```bash
# Copier le template de configuration
cp .env.example .env
```

Editer `.env` avec vos valeurs :

| Variable | Description | Requis |
|----------|-------------|--------|
| `SONAR_TOKEN` | Token API SonarCloud ([generer ici](https://sonarcloud.io/account/security)) | Pour integration Sonar |
| `SONAR_PROJECT_KEY` | Cle du projet (format: `org_repo`) | Pour integration Sonar |
| `WS_BASE_URL` | URL WebSocket pour notifications | Optionnel |
| `TEST_MODE` | Mode test (1=actif, 0=desactive) | Optionnel |

### 3. Initialisation

```bash
# Initialiser la base AgentDB
python .claude/scripts/bootstrap.py --full
```
---

## Navigation

| Section | Description |
|---------|-------------|
| [Introduction](01-introduction-et-philosophie.md) | Philosophie et concepts fondamentaux |
| [Architecture](02-architecture-globale.md) | Diagrammes et flux de donnees |
| [Configuration](03-analyse-configuration.md) | Fichiers YAML et parametres |
| [Outils MCP](04-mcp-et-outils.md) | Les 10 outils AgentDB |
| [Guide Pratique](05-guide-lineaire.md) | Tutoriel pas a pas |
| [Maintenance](06-maintenance-et-tests.md) | Tests et maintenance |
| [AgentDB](AGENTDB.md) | Reference complete AgentDB |
| [Agents](AGENTS.md) | Documentation des 8 agents |

---

## Verdicts

| Score | Verdict | Action |
|-------|---------|--------|
| >= 80 | APPROVE | Peut etre merge |
| >= 60 | REVIEW | Review humaine recommandee |
| >= 40 | CAREFUL | Review approfondie requise |
| < 40 | REJECT | Ne pas merger |
