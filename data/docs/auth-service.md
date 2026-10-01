# auth-service

Handles customer login, OAuth tokens and service-to-service tokens. Team: **identity**. Tier-1.

## Overview

auth-service is written in Go 1.22. Every request that reaches api-gateway is checked against auth-service, so its latency directly affects the whole platform. Token validation is cached in api-gateway for 60 seconds to reduce load.

## Customer authentication

- Customers log in with email and password or with Google / Apple sign-in.
- Successful login returns an access token (valid 15 minutes) and a refresh token (valid 30 days).
- After 5 failed logins in 10 minutes, the account is locked for 15 minutes.
- Passwords are hashed with Argon2id. auth-service never logs passwords or tokens.

## Service tokens

Internal services get short-lived service tokens (valid 10 minutes) by calling `POST /v2/service-tokens` over mTLS. Each token lists the scopes the calling service is allowed to use, for example `payments:charge`.

## Key rotation

Signing keys rotate automatically every 30 days. The previous key stays valid for 24 hours after rotation so tokens issued just before the rotation keep working. If a key may have leaked, the identity team can rotate immediately with `shopflow auth rotate-keys --now`.

## Running locally

Runs on port 8004. Locally, any email with the password `local-dev` can log in.
