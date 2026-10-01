# Architecture Overview

ShopFlow is an online store built from ten services. This page explains how they fit together.

## Services and owners

| Service | Team | Language | Tier | Purpose |
|---|---|---|---|---|
| api-gateway | platform | Go | tier-1 | Single entry point for web and mobile clients |
| order-service | checkout | Python | tier-1 | Carts, checkout and order lifecycle |
| payments-service | payments | Java | tier-1 | Card payments, refunds, settlement |
| inventory-service | logistics | Go | tier-1 | Stock levels and reservations |
| auth-service | identity | Go | tier-1 | Login, OAuth tokens, service tokens |
| user-service | identity | Python | tier-2 | Customer profiles and addresses |
| notification-service | growth | TypeScript | tier-2 | Email, SMS and push notifications |
| shipping-service | logistics | Python | tier-2 | Carrier integrations and tracking |
| search-service | discovery | Java | tier-2 | Product search and filters |
| analytics-service | data | Python | tier-3 | Reporting and dashboards |

## Service tiers

- **tier-1:** customers cannot shop without it. 99.95% availability target, 24/7 on-call, strict deployment windows.
- **tier-2:** important but the store keeps working if it is down. 99.9% target, 24/7 on-call.
- **tier-3:** internal. 99.5% target, business-hours support only.

## Request flow for a purchase

1. The client calls api-gateway, which checks the token with auth-service.
2. api-gateway forwards the checkout request to order-service.
3. order-service reserves stock in inventory-service.
4. order-service asks payments-service to charge the customer.
5. On success, order-service publishes an `order.placed` event to RabbitMQ.
6. notification-service sends the confirmation email, and shipping-service books a carrier.

## Infrastructure

- Everything runs on Kubernetes in two regions (eu-west and us-east).
- Each service owns its own PostgreSQL database. Services never read another service's database directly. They call its API or consume its events.
- Redis is used for caching and rate limiting.
- RabbitMQ carries asynchronous events between services.
- Metrics and dashboards are in Grafana, logs in Loki, traces in Tempo.
