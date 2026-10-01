# inventory-service

Tracks stock levels across warehouses and reserves stock during checkout. Team: **logistics**. Tier-1.

## Overview

inventory-service is written in Go 1.22. It stores stock per product per warehouse in PostgreSQL and keeps a Redis cache of available quantities for fast reads by search-service and the product pages.

## Reservations

- order-service calls `POST /v2/reservations` with the items in a cart.
- A reservation holds the stock for **15 minutes**. If the order is not paid in that time, the reservation expires and the stock becomes available again.
- When an order is paid, the reservation is confirmed and the stock is permanently deducted.
- Reservations use row-level locks so two customers can never buy the last item at the same time.

## Stock updates

Warehouses send stock updates through a nightly CSV import and through real-time events from the warehouse system. Imports run at 04:00 UTC. If an import fails, the on-call engineer is paged and the previous day's stock levels remain in place.

## Common alerts

- **Reservation latency high:** usually lock contention during a flash sale. Check the "hot products" panel.
- **Cache out of sync:** run `shopflow inventory resync-cache` to rebuild the Redis cache from the database.

## Running locally

Runs on port 8003. Seed local stock with `shopflow inventory seed`.
