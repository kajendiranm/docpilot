# On-call Guide

What it means to be on call at ShopFlow and how to handle a page.

## Rotation

- Each team with a tier-1 or tier-2 service runs its own weekly rotation, Monday 10:00 to Monday 10:00.
- There is always a primary and a secondary on-call engineer. If the primary does not acknowledge a page within 5 minutes, it escalates to the secondary, and after another 10 minutes to the engineering manager.
- Schedules live in PagerDuty. Swap shifts directly in PagerDuty and tell your team in its channel.
- On-call engineers get one day off in lieu for every week on call that included an out-of-hours page.

## Before your shift

- Check you can log in to PagerDuty, Grafana, the internal portal and the production read-only console.
- Read the handover notes from the previous on-call engineer in your team's channel.
- Make sure your laptop is charged and you have a working internet connection wherever you will be.
- Review any deployments planned for the week (see the deployment runbook).

## When you get paged

1. **Acknowledge** the page in PagerDuty within 5 minutes.
2. **Assess** the impact: open the service dashboard and check error rate, latency and traffic.
3. **Decide the severity** using the levels in the incident response guide. If it is high or critical, declare an incident straight away.
4. **Mitigate first, investigate later.** Rolling back the latest deployment is the most common fix. Check #deploys for recent changes to your service.
5. **Communicate.** Post updates in the incident channel at least every 30 minutes.
6. **Hand over** if the incident runs past your shift or you need rest. Never stay on an incident for more than 4 hours without a break.

## Useful dashboards and tools

- Grafana: one dashboard per service, named after it (for example "payments-service overview").
- Logs: `shopflow logs <service> --env prod --since 30m`
- Recent deploys: `shopflow deploy history <service>`
- Runbooks for each alert are linked from the alert itself.

## Handover

At the end of your week, post a handover note in your team channel with: pages received, incidents and their status, anything still being watched, and suggestions for improving alerts or runbooks.
