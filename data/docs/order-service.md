# order-service

Owns carts, checkout and the lifecycle of an order. Team: **checkout**. Tier-1.

## Overview

order-service is a Python 3.11 FastAPI application with its own PostgreSQL database. It coordinates checkout: it reserves stock with inventory-service, charges the customer through payments-service and publishes order events for other services.

## Order lifecycle

An order moves through these states:

`created` → `stock_reserved` → `paid` → `fulfilled` → `delivered`

It can also move to `cancelled` (before payment) or `refunded` (after payment). If payment fails, the stock reservation is released automatically after 15 minutes.

## Key endpoints

- `POST /v2/carts/{cart_id}/checkout` starts checkout. Requires an `Idempotency-Key` header.
- `GET /v2/orders/{order_id}` returns an order and its status.
- `GET /v2/orders?customer_id=...` lists a customer's orders using cursor pagination.
- `POST /v2/orders/{order_id}/cancel` cancels an unpaid order.

## Events published

- `order.placed` when payment succeeds.
- `order.cancelled` and `order.refunded` on those transitions.

Events go to the `orders` exchange in RabbitMQ.

## Dependencies

inventory-service, payments-service, RabbitMQ, PostgreSQL and Redis (for cart caching). If payments-service is slow, checkout latency rises directly, so check the payments dashboard first when order-service p99 latency alerts fire.

## Running locally

See the "Local development" section of the developer setup guide. order-service listens on port 8001.
