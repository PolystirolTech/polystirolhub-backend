# PolystirolHub Backend

Backend for PolystirolHub, built with FastAPI, PostgreSQL, Redis, and Docker.

## Requirements

- Python 3.11+
- Docker & Docker Compose

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repo-url>
    cd polystirolhub-backend
    ```

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    .\venv\Scripts\activate  # Windows
    # source venv/bin/activate # Linux/Mac
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Environment Variables:**
    Copy `.env.example` to `.env` (create one if missing) and adjust settings.
    ```ini
    POSTGRES_SERVER=localhost
    POSTGRES_USER=postgres
    POSTGRES_PASSWORD=postgres
    POSTGRES_DB=app
    ```

## Running the App

1.  **Start Database & Redis:**
    ```bash
    docker-compose up -d
    ```

2.  **Run Migrations:**
    ```bash
    alembic upgrade head
    ```

3.  **Start the Server:**
    ```bash
    uvicorn app.main:app --reload
    ```

    The API will be available at `http://localhost:8000`.
    Swagger UI: `http://localhost:8000/docs`.

## CI/CD

GitHub Actions are configured to run on `main` and `dev` branches.
- **Linting**: Ruff
- **Testing**: Pytest
