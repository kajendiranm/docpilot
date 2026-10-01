# API Conventions

Rules every ShopFlow HTTP API must follow. They keep our services consistent for each other and for the mobile and web apps. Owned by the Platform team.

## URLs and versioning

- Use plural nouns for resources: `/orders`, `/orders/{order_id}/items`.
- Use kebab-case in paths and snake_case in JSON fields.
- Every public API is versioned in the path: `/v2/orders`. `/v1` endpoints are deprecated and will be removed at the end of the year.
- A breaking change requires a new version. Adding optional fields is not a breaking change.

## Requests and responses

- JSON only, UTF-8, with `Content-Type: application/json`.
- Timestamps are ISO 8601 in UTC, for example `2026-03-14T09:30:00Z`.
- Money is an object with an integer amount in minor units and a currency code: `{"amount": 1999, "currency": "EUR"}`. Never use floats for money.
- IDs are opaque strings. Clients must not parse them.

## Pagination

List endpoints use cursor pagination:

- Request: `GET /v2/orders?limit=50&cursor=<cursor>`. The default `limit` is 20 and the maximum is 100.
- Response: `{"data": [...], "next_cursor": "..."}`. `next_cursor` is `null` on the last page.
- Do not use offset pagination for new endpoints. It becomes slow and inconsistent on large tables.

## Errors

Errors use standard HTTP status codes and a consistent body:

```json
{"error": {"code": "order_not_found", "message": "Order 123 does not exist", "request_id": "req_abc"}}
```

- `400` validation error, `401` not authenticated, `403` not allowed, `404` not found, `409` conflict, `422` business rule violated, `429` rate limited, `5xx` server error.
- `code` is a stable, machine-readable string. `message` is for humans and may change.
- Always include the `request_id` so support can find the request in the logs.

## Authentication

- Internal service-to-service calls use mTLS plus a short-lived service token issued by auth-service.
- Public endpoints use OAuth 2.0 bearer tokens issued by auth-service.
- Never put tokens or personal data in URLs or logs.

## Idempotency

`POST` endpoints that create money movements or orders must accept an `Idempotency-Key` header. Repeating a request with the same key within 24 hours returns the original response instead of creating a duplicate.

## Rate limiting

api-gateway enforces rate limits per client. When a client is limited it receives `429` with a `Retry-After` header in seconds.
