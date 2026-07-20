# Confirmed product decisions

Updated from the customer discovery answers on 20 July 2026.

## Business model

- The first deployment is for one Shisha Bar.
- The product must remain reusable and multi-tenant so the same solution can later be sold to other venues.
- Credit is a closed-loop balance: it is valid only at the issuing venue.
- Customer-to-customer transfers and cash withdrawals are not supported in the initial product.

## Customer value proposition

- Customers can prepay, for example, EUR 200 at the beginning of the month.
- The venue may grant a configurable bonus, initially proposed as 10%, so EUR 200 creates EUR 220 usable credit.
- Bonus credit must be recorded separately from paid credit in the ledger so reporting, refunds and future tax treatment remain clear.

## Platforms

- Apple/iOS is the first native target.
- The initial implementation remains a mobile-first PWA and REST API so it can launch quickly and later support an iOS client without replacing the backend.
- Android can use the same API in a later phase.

## Payments and cards

- Customers must eventually be able to top up online themselves.
- The payment provider must be selected before implementation. Stripe is a likely option, but not yet a confirmed product decision.
- A lost card can be blocked.
- After identity verification, the remaining balance can be moved to a replacement card.
- All card replacement, blocking and balance movement operations require an audit event.

## POS and compliance

- The venue already has a POS system; its vendor and available API still need to be confirmed.
- Every wallet purchase should be linked to an external order or receipt reference when the POS integration is available.
- POS requests must use idempotency keys to prevent duplicate charges.
- Financial and tax treatment must be confirmed with the venue's German tax adviser before production launch.

## Delivery phases

All discussed capabilities remain in scope, but they are delivered in controlled phases to keep the first release reliable.

### Phase 1 — secure wallet foundation

- Customer, employee and manager roles
- QR card and balance
- Manager top-ups
- Staff purchase deductions
- Refunds and corrections
- Transaction history
- Audit log
- Card blocking
- Mobile-first PWA

### Phase 1.1 — customer funding and card lifecycle

- Customer online top-up
- Configurable 10% bonus campaign
- Separation of paid and bonus credit
- Lost-card replacement and balance transfer
- Apple-ready authentication and API hardening

### Phase 2 — engagement

- Loyalty points and rewards
- Promotions and discounts
- Reservations
- Competitions and campaigns
- Push notifications

### Phase 3 — POS integration

- POS connector after the vendor/API is confirmed
- Receipt and order synchronization
- Idempotent wallet payments
- Reconciliation and exception reporting
