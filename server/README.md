Requirements:
    1. fastapi
    2. sqlalchemy
    3. asyncpg
    4. alembic
    5. uvicorn
    6. pydantic
    7. python-dotenv
    8. python-jose
    9. passlib
    10. httpx
    11. psutil


Structures:
    1. constants: save hardcoded variables and values here
    2. db: crud operations and db setup code
    3. exceptions: create any customized exceptions
    4. models: declare all the required data models
    5. routers: declare and define all routers
    6. schemas: to define the schemas
    7. services: business logic code for each service
    8. init_db: db initialization code
    9. dependencies: all the dependencies defined
    10. main: entry point
    11. auth: authentication and authorization modules
    12. monitoring: application monitoring and metrics
    13. scripts: utility scripts for database and system operations

workflow_orchestrator/server/
├── alembic_env/
│   ├── __init__.py
│   ├── env.py
│   ├── README
│   └── script.py.mako
│
├── app/
│   ├── auth/
│   │   ├── v1/
│   │   │   └── __init__.py
│   │   └── __init__.py
│   │
│   ├── constants/
│   │   └── __init__.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   └── database.py
│   │
│   ├── exceptions/
│   │   ├── __init__.py
│   │   └── http_exceptions.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── users.py
│   │   ├── workflow.py
│   │   └── workspace.py
│   │
│   ├── monitoring/
│   │   └── __init__.py
│   │
│   ├── routers/
│   │   └── __init__.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── users.py
│   │   ├── workflow_schemas.py
│   │   └── workspace_schemas.py
│   │
│   ├── scripts/
│   │   └── check_db_connection.py
│   │
│   ├── services/
│   │   └── __init__.py
│   │
│   ├── __init__.py
│   ├── config.py
│   ├── main.py                    👈 (Main FastAPI application entry point)
│   └── requirements.txt
│
├── tests/
│   ├── routers/
│   │   └── v1/
│   │       └── __init__.py
│   └── __init__.py
│
├── alembic.ini
├── config_dev.json
├── config_pre_prod.json
├── config_prod.json
├── config_loader.py
├── dependencies.py
├── init_db.py
├── poetry.lock
├── pyproject.toml
├── pytest.ini
├── README.md
├── Readme.txt
├── CONFIG.md
├── CONFIGURATION.md
└── CONFIG_GUIDE.md
