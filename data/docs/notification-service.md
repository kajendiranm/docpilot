# notification-service

Sends email, SMS and push notifications to customers. Team: **growth**. Tier-2.

## Overview

notification-service is a Node.js 20 TypeScript service. It consumes events from RabbitMQ (for example `order.placed`) and sends the matching message through our email, SMS and push providers. It does not decide *when* to notify. Other services publish events, and notification-service only turns them into messages.

## Templates

- Templates live in the `templates/` folder of the service, one folder per event and channel.
- Templates are translated into English, German, French and Spanish. Missing translations fall back to English.
- Changes to templates go through normal code review and deploy like any other change.

## Delivery and retries

- Failed sends are retried 3 times with exponential backoff (1, 5 and 25 minutes).
- After the last retry, the message goes to a dead-letter queue and appears on the "notifications DLQ" dashboard.
- Customers who unsubscribe from marketing still receive transactional messages such as order confirmations and password resets.

## Common alerts

- **Queue backlog growing:** usually the email provider is slow. Check the provider's status page before restarting anything.
- **DLQ size increasing:** look at the error reason on the dashboard. Bad phone numbers are the most common cause for SMS.

## Running locally

Runs on port 8006. Locally, all messages go to MailHog at `localhost:8025` instead of real customers.
