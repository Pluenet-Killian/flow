"""
AgentDB Tests - Suite de tests.

Ce package contient les tests unitaires et d'intégration pour AgentDB.

Structure prévue:
- test_db.py         : Tests de la connexion et helpers DB
- test_models.py     : Tests des modèles de données
- test_crud.py       : Tests des opérations CRUD
- test_queries.py    : Tests des requêtes complexes (graphe)
- test_indexer.py    : Tests de l'indexeur de code
- test_mcp_tools.py  : Tests des outils MCP
- test_integration.py: Tests d'intégration bout-en-bout

Usage:
    # Tous les tests
    pytest .claude/tests/

    # Tests spécifiques
    pytest .claude/tests/test_crud.py

    # Avec couverture
    pytest --cov=agentdb .claude/tests/
"""
