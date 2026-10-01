# Developer Setup Guide

This guide gets a new ShopFlow engineer from a fresh laptop to running services locally. Expect it to take about an hour. If something here is wrong, tell the Platform team in #platform-help.

## Prerequisites

Install the following before you start:

- **Python 3.8** (we recommend installing it with `pyenv`)
- **Go 1.22** for the Go services (inventory, auth, api-gateway)
- **Java 21** and Gradle for the Java services (payments, search)
- **Node.js 20** for notification-service
- **Docker Desktop** with at least 6 GB of memory allocated
- The `shopflow` CLI: `brew install shopflow/tap/shopflow-cli`

You also need access to the GitHub organisation `shopflow` and to the shared 1Password vault "Engineering – Dev". Ask your manager to request both on your first day.

## Getting the code

All services live in a single monorepo:

```bash
git clone git@github.com:shopflow/platform.git
cd platform
shopflow bootstrap        # installs git hooks and checks your toolchain
```

`shopflow bootstrap` prints a red line for every missing tool. Fix those before continuing.

## Local development

Every service can run on its own against shared local infrastructure (Postgres, Redis and RabbitMQ in Docker).

1. Start the shared infrastructure from the repo root:
   ```bash
   docker compose -f infra/local/docker-compose.yml up -d
   ```
2. Copy the example environment file for the service you want, for example the order service:
   ```bash
   cp services/order-service/.env.example services/order-service/.env
   ```
3. Install dependencies and apply database migrations:
   ```bash
   cd services/order-service
   poetry install
   poetry run alembic upgrade head
   ```
4. Run the service:
   ```bash
   poetry run uvicorn order_service.main:app --reload --port 8001
   ```
5. Check it is healthy: `curl localhost:8001/health` should return `{"status": "ok"}`.

Local ports follow a convention: order 8001, payments 8002, inventory 8003, auth 8004, user 8005, notification 8006, shipping 8007, search 8008, api-gateway 8080.

To run the whole stack at once, use `shopflow up`. It needs about 10 GB of RAM, so most people run only the services they are changing.

## Running tests

- Python services: `poetry run pytest`
- Go services: `go test ./...`
- Java services: `./gradlew test`
- Node services: `npm test`

Integration tests need the shared infrastructure from step 1 to be running. CI runs the same commands, so if tests pass locally they should pass in CI.

## Troubleshooting

- **Port already in use:** another service or an old container is holding the port. Run `shopflow ps` to see what is running and `shopflow down` to stop everything.
- **Migrations fail with "relation already exists":** your local database is out of date. Reset it with `shopflow db reset order-service`.
- **Docker runs out of memory:** raise the Docker Desktop memory limit to at least 6 GB.
- **Cannot pull private images:** run `shopflow login` to refresh your registry credentials.
