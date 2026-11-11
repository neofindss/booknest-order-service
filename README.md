# BookNest order service

This repository is the BookNest order bounded context. It owns orders. It does not read the catalogue database.

Placing an order calls the catalog service to reserve stock. Cancelling an order calls the catalog service to release that stock. The price stored on an order is the price returned by the catalog service.

## Run the tests

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

## Run with Docker Compose

From the assignment folder that contains `docker-compose.yml`:

```powershell
docker compose up --build
```

Order API: `http://localhost:8002`  
Interactive API docs: `http://localhost:8002/docs`

`CATALOG_BASE_URL` must point at the catalog service. Compose sets this to `http://catalog-service:8000`.

## Run on Kubernetes

Deploy the whole BookNest system from the assignment root. If the images are missing, run `docker compose build`, then `.\scripts\deploy-minikube.ps1`. This service's manifests are applied as part of that. The deployment uses image `booknest-order:1.0.0` with `imagePullPolicy: Never`, so a same-tag update needs the script's rollout restart (the script already does it). The full start-to-stop list is in `docs/STEP_BY_STEP.md`.

The optional autoscaler is in `k8s/optional/order-hpa.yaml`.

## API

| Method | Path | Kind |
| --- | --- | --- |
| POST | `/api/v1/orders` | Command: PlaceOrder |
| POST | `/api/v1/orders/{orderId}/cancellations` | Command: CancelOrder |
| GET | `/api/v1/orders/{orderId}` | Query: GetOrder |
| GET | `/api/v1/orders?customerEmail=` | Query: ListCustomerOrders |
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness, checks this service's MongoDB |

Example:

```powershell
Invoke-RestMethod http://localhost:8002/api/v1/orders -Method Post -ContentType application/json -Body '{"customerName":"Ananya Shah","customerEmail":"ananya.shah@example.com","items":[{"bookId":"book-kitchen-orbits","quantity":1}]}'
```
