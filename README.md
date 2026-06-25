GameMetrix
==========

GameMetrix is a dark, minimalist game score explorer. The current version has a
FastAPI backend with SQLAlchemy models, seeded mock game data, and a Vite React
frontend that filters games by search, genre, year, score, and sort order.

## Run PostgreSQL

```powershell
docker compose up -d db
```

The default backend database URL is:

```text
postgresql+psycopg://admin:password123@localhost:5432/gamemetrix
```

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
