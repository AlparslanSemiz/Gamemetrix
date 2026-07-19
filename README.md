GameMetrix
==========

GameMetrix is a dark, minimalist game score explorer. The current version has a
FastAPI backend with SQLAlchemy models, seeded mock game data, and a Vite React
frontend that filters games by search, genre, year, score, and sort order.

## Run PostgreSQL

```powershell
$env:POSTGRES_USER="gamemetrix"
$env:POSTGRES_PASSWORD="<choose-a-local-password>"
docker compose up -d db
```

Set `backend\.env` with a matching PostgreSQL database URL:

```text
DATABASE_URL=postgresql+psycopg://gamemetrix:<choose-a-local-password>@localhost:5432/gamemetrix
```

`DATABASE_URL` is required. The backend intentionally supports one runtime
database: PostgreSQL.

## Run Backend

```powershell
python -m pip install -r backend\requirements.txt
cd backend
python -m uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`.

## Run Frontend

```powershell
cd frontend
npm install
npm run dev
```

The app runs at `http://127.0.0.1:5173`.
