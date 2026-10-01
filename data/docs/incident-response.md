# Incident Response Guide

How ShopFlow declares, runs and learns from incidents.

## Severity levels

| Severity | Definition | Example | Response time |
|---|---|---|---|
| **critical** | Customers cannot place orders or pay, or data is at risk | Checkout returns errors for all users | Immediately, 24/7 |
| **high** | A major feature is broken or badly degraded for many users | Search is down; payments slow for 20% of users | Within 15 minutes, 24/7 |
| **medium** | Partial degradation with a workaround | Order confirmation emails delayed by 1 hour | Within 1 hour, business hours |
| **low** | Minor issue with little customer impact | An internal report is wrong | Next business day |

When unsure between two levels, pick the higher one. You can always lower it later.

## Declaring an incident

Run `shopflow incident new --service <service> --severity <level> --title "<short title>"`. This:

- creates a Slack channel named `#inc-<number>`,
- pages the on-call engineer for the service,
- records the incident with its start time.

For critical incidents, also page the incident commander rotation with `shopflow incident page-ic`.

## Roles

- **Incident commander (IC):** coordinates the response and makes decisions. Does not debug.
- **Operations lead:** the engineer doing the hands-on investigation and fix.
- **Communications lead:** posts updates to #status and to customer support every 30 minutes for high and critical incidents.

For low and medium incidents, the on-call engineer usually plays all three roles.

## Resolving an incident

An incident is resolved when customer impact has ended and metrics are back within the SLO. Mark it resolved with `shopflow incident resolve <number>`, which records the resolution time. Keep the channel open for follow-up discussion.

## Postmortems

- Required for every high and critical incident, and for any incident that lasted longer than 4 hours.
- Write it within 5 business days using the template in the internal portal.
- Postmortems are **blameless**: focus on systems and processes, not individuals.
- Each postmortem lists action items with owners and due dates. Action items are tracked as tickets.
