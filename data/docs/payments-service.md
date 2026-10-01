# payments-service

Handles card payments, refunds and daily settlement with our payment provider. Team: **payments**. Tier-1.

## Overview

payments-service is a Java 21 Spring Boot application. It is the only service allowed to talk to the external payment provider, and the only one that stores payment references. It never stores full card numbers. Card details go straight from the client to the provider, and we keep only a token.

## Key flows

- **Charge:** order-service calls `POST /v2/payments` with an amount, currency, customer token and `Idempotency-Key`. payments-service calls the provider and returns `succeeded`, `failed` or `requires_action` (for 3-D Secure).
- **Refund:** `POST /v2/payments/{payment_id}/refunds`. Partial refunds are allowed. Refunds over €1,000 need a second approval in the admin portal.
- **Settlement:** a nightly job (01:00–03:00 UTC) reconciles our records with the provider's settlement report. Mismatches create a ticket for the payments team.

## Reliability notes

- The provider occasionally times out. Calls use a 3-second timeout with up to 2 retries, always with the same idempotency key, so a customer is never charged twice.
- If the provider is down, payments-service returns `503` and order-service shows "Payment temporarily unavailable". We do not queue payments for later.
- The most important metric is the **payment success rate**, which should stay above 99.5%.

## Deploying

payments-service has stricter deployment rules than other services: two approvals, a longer canary and no deploys during settlement. See "Deploying payments-service" in the deployment runbook.

## Running locally

Runs on port 8002. Locally it uses the provider's sandbox, so no real money moves. Sandbox keys are in the "Engineering – Dev" 1Password vault.
