# TaskFlow API + React Dashboard 🚀

A production-ready full-stack task management application demonstrating **FastAPI**, **PostgreSQL**, **React + TypeScript**, **Docker**, and **microservices-ready patterns**.

---

## Features

**Backend (FastAPI):**
- ✅ User registration & JWT authentication
- ✅ CRUD tasks with status workflow (todo → in_progress → done → archived)
- ✅ PostgreSQL with SQLAlchemy async ORM
- ✅ Alembic migrations (versioned DB schema)
- ✅ Rate limiting via SlowAPI
- ✅ CORS configuration
- ✅ Dockerized with health checks
- ✅ Structured logging (ready)
- ✅ OpenAPI docs (`/docs`)

**Frontend (React):**
- ✅ TypeScript + React Query for data fetching
- ✅ Authentication flow with JWT storage
- ✅ Kanban-style board (columns per status)
- ✅ Responsive design with Tailwind CSS
- ✅ Create, update, delete tasks
- ✅ Cycle status workflow
- ✅ Priority badges

**DevOps:**
- ✅ Docker Compose (Postgres, Redis, Backend, Frontend)
- ✅ Separate service containers
- ✅ Volume persistence for DB
- ✅ Nginx reverse proxy for frontend
- ✅ API proxy from frontend to backend

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 18+ (for local frontend dev)

### Run with Docker Compose

```bash
cd demo-01-taskflow
docker-compose up --build
```

This starts:
- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000/docs (Swagger)
- **PostgreSQL:** localhost:5432
- **Redis:** localhost:6379

### Access the App

1. Open http://localhost:3000
2. Register a new user via API: POST `/api/v1/auth/register`
   - Use `/docs` endpoint to register easily
3. Login via frontend form
4. Start managing tasks!

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login (JWT) |
| GET  | `/api/v1/users/me` | Get current user |
| PUT  | `/api/v1/users/me` | Update user profile |
| GET  | `/api/v1/tasks/` | List tasks (filter by `status`) |
| POST | `/api/v1/tasks/` | Create task |
| GET  | `/api/v1/tasks/{id}` | Get task |
| PUT  | `/api/v1/tasks/{id}` | Update task |
| DELETE| `/api/v1/tasks/{id}` | Delete task |
| GET  | `/health` | Health check |

---

## Development

### Backend (local)
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend (local)
```bash
cd frontend
npm install
npm run dev
```

### Running Migrations
```bash
cd backend
alembic upgrade head
```

---

## Best Practices Demonstrated

1. **Async database operations** (asyncpg + AsyncSession)
2. **Dependency injection** for database and auth
3. **Pydantic v2** schemas with strict validation
4. **JWT authentication** with expiration
5. **Rate limiting** per IP
6. **CORS** restricted to known origins
7. **SQLAlchemy** models with relationships
8. **Separation of concerns** (models, schemas, routers, utils)
9. **Error handling** with global exception handlers
10. **Docker multi-stage builds** (frontend optimization)
11. **TypeScript strict mode** with React Query
12. **Component composition** with clean separation

---

## Environment Variables

Create `.env` in `backend/`:

```env
DEBUG=false
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost/taskflow
SECRET_KEY=your-super-secret-jwt-key-change-in-production
ALLOWED_ORIGINS=http://localhost:3000
RATE_LIMIT_TIMES=100
RATE_LIMIT_SECONDS=60
```

---

## Testing

Run backend tests:
```bash
cd backend
pytest
```

Run frontend tests:
```bash
cd frontend
npm test
```

---

## Next Steps

- Add WebSocket for real-time updates
- Implement email notifications (SendGrid)
- Add role-based access control (RBAC)
- Implement audit logging
- Add Prometheus metrics endpoint
- Set up CI/CD pipeline (GitHub Actions)
- Add end-to-end tests (Playwright)
- Horizontal scaling with Kubernetes
- API versioning strategy

---

## License

MIT