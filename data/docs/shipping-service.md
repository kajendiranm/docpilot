# shipping-service

Books carriers for paid orders and tracks parcels. Team: **logistics**. Tier-2.

## Overview

shipping-service is a Python 3.11 service. It listens for `order.placed` events, picks the cheapest carrier that meets the delivery promise, books the shipment and stores the tracking number. Customers see tracking updates in the app through the `GET /v2/shipments/{order_id}` endpoint.

## Carriers

We integrate with three carriers: DHL, UPS and a local same-day courier in large cities. Carrier choice is based on destination, parcel weight and the delivery speed the customer paid for. Carrier API keys are stored in the secrets manager, never in the repository.

## Tracking updates

Carriers send status updates by webhook. If a webhook is missed, a job polls each carrier every 2 hours for shipments that have not changed status in 24 hours.

## Common alerts

- **Carrier booking failures:** one carrier's API is down. shipping-service automatically falls back to the next cheapest carrier, so this is usually not urgent unless all carriers fail.
- **Webhook errors:** usually an expired webhook secret. The rotation steps are in the shipping-service README.

## Running locally

Runs on port 8007. Locally, carrier calls go to mock servers started by `shopflow up shipping-service`.
