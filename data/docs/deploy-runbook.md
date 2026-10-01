# Deployment Runbook

How ShopFlow ships code to production. Owned by the Platform team.

## Overview

All services deploy through the same pipeline: merge to `main` → CI builds and tests → image pushed to the registry → staging deploy → automated smoke tests → production canary → full rollout. Deployments are triggered with the `shopflow deploy` CLI or the "Deploy" button in the internal portal. Every deployment is recorded with its version, status (`success`, `failed` or `rolled_back`) and who triggered it.

## Deployment windows

- Tier-1 services (order, payments, inventory, auth, api-gateway) deploy **Monday to Thursday, 10:00–16:00** local time.
- Tier-2 and tier-3 services may deploy any weekday.
- No production deployments on Fridays after 12:00, on weekends, or during a declared incident, unless the deploy is the fix.
- A code freeze applies for the two weeks around Black Friday. Exceptions need approval from the VP of Engineering.

## Standard deployment steps

1. Make sure the change is merged to `main` and the CI pipeline is green.
2. Deploy to staging:
   ```bash
   shopflow deploy <service> --env staging --version <git-sha>
   ```
3. Wait for the staging smoke tests to pass (about 5 minutes). Results appear in #deploys.
4. Start the production canary, which sends 5% of traffic to the new version:
   ```bash
   shopflow deploy <service> --env prod --version <git-sha> --canary 5
   ```
5. Watch the service dashboard for 15 minutes. Error rate and p99 latency must stay within the service's SLO.
6. Promote to 100%: `shopflow deploy promote <service>`.
7. Post a short note in #deploys with the version and a link to the change.

## Deploying payments-service

payments-service handles real money, so it has extra rules on top of the standard steps:

- Deploys need **two approvals**: one from the payments team and one from the on-call engineer.
- The canary runs for **30 minutes** instead of 15, starting at 2% of traffic.
- Before promoting, check the "Payment success rate" panel. It must stay above 99.5%.
- Database migrations for payments must be backward compatible and must ship in a separate deploy from the code that uses them.
- Never deploy payments during the nightly settlement job (01:00–03:00 UTC).

The command is the same, with the payments canary settings:

```bash
shopflow deploy payments-service --env prod --version <git-sha> --canary 2 --bake 30m
```

## Rolling back

If error rate or latency goes above the SLO during the canary or after promotion, roll back immediately. Do not try to fix forward under pressure.

```bash
shopflow deploy rollback <service>
```

Rollback returns traffic to the previous version within about 2 minutes. The deployment is then marked `rolled_back`. After a rollback, open an incident if customers were affected (see the incident response guide) and post in #deploys.

## Failed deployments

A deployment is marked `failed` when it never reaches production, for example because staging smoke tests fail or the image cannot start. Failed deployments do not affect customers, but repeated failures on the same service should be raised with the owning team. Check the pipeline logs with `shopflow deploy logs <service> --last`.
