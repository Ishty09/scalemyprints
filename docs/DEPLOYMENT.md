# Deployment Guide

A validation-first phased rollout. Each phase has a spending gate; you only pay for the next phase's infrastructure once the previous phase's results justify it.

| Phase | Description                          | Spend       | Status     |
| ----- | ------------------------------------ | ----------- | ---------- |
| **A** | Build MVP (this codebase)            | ~$31        | ✅ shipped |
| **B** | Beta with 20 invited users           | $0          | ⏳ next    |
| **C** | Pre-revenue prep                     | ~$26        | ⬜          |
| **D** | Revenue go-live (Lemon Squeezy)      | pay-as-earn | ⬜          |
| **E** | LLC + scale infrastructure           | ~$571       | ⬜          |

## Phase A: Build (current)

Already complete. Total cost: **~$31** (domain).

- Code: shipped
- Domain: registered
- Test infrastructure: free GitHub Actions, free Supabase tier, free Cloudflare Pages
- Workers: deployed on Hetzner CX11 (€4/mo) — see "Workers deploy" below

## Phase B: Beta validation

**Goal:** Prove that someone wants this before charging anyone. Twenty hand-invited users, two weeks. Total spend: $0.

### Setup

1. **Supabase** — already free tier (≤ 500MB storage, 50k monthly active users). No upgrade needed.
2. **Cloudflare Pages** — auto-deploys `apps/web` on push to `main`. Free tier (500 builds/month).
3. **Workers on Hetzner** — already running from Phase A.
4. **Sentry** — free tier (5k errors/month).
5. **PostHog** — free tier (1M events/month).
6. **Resend** — free tier (3k emails/month, 100/day).

### Invite mechanics

- Add invitees' emails to `waitlist` with `status='invited'`
- Send invite emails via Resend (`/api/admin/invite-batch`)
- Track signup conversions via PostHog
- Manually review weekly with `SELECT count(*) FROM tm_searches GROUP BY user_id`

### Validation gates (must hit before Phase C)

- ≥ 8/20 users complete a Trademark Shield search within 48h
- ≥ 5/20 users return for a second session within 7 days
- ≥ 3/20 users explicitly say they'd pay (interview confirmation)

If any gate fails, do not proceed. Fix the product before spending more.

## Phase C: Pre-revenue prep

**Goal:** Clear the legal + payment bar so you can charge tomorrow. Total: **~$26**.

### One-time costs

| Item                                    | Cost     |
| --------------------------------------- | -------- |
| Termly (Privacy Policy + Terms)         | $10/mo   |
| Lemon Squeezy account                   | $0 setup |
| Mailgun verified sending domain         | $0       |
| **Total**                               | **~$26** |

### Lemon Squeezy setup

Lemon Squeezy is the **Merchant of Record** — they handle VAT, sales tax, and EU compliance for you. You don't need an LLC to start.

1. Create account at https://lemonsqueezy.com (5-min signup, accepts personal/freelance setup)
2. Add product variants matching `BUNDLES` and `TRADEMARK_SHIELD_PLANS` from `packages/contracts/src/pricing.ts`
3. Copy product IDs into `.env`:
   ```
   LEMONSQUEEZY_API_KEY=...
   LEMONSQUEEZY_STORE_ID=...
   LEMONSQUEEZY_WEBHOOK_SECRET=...
   LEMONSQUEEZY_PRODUCT_TRADEMARK_STARTER=...
   LEMONSQUEEZY_PRODUCT_CORE_BUNDLE=...
   ```
4. Configure webhook → `https://api.scalemyprints.com/api/v1/webhooks/lemonsqueezy`

## Phase D: Revenue go-live

Subscriptions start. Costs scale with users.

### Production deployment

#### Workers on Hetzner

```bash
# On the VPS, one-time setup:
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER
git clone https://github.com/scalemyprints/scalemyprints /opt/scalemyprints
cd /opt/scalemyprints
cp .env.example .env
$EDITOR .env  # fill in Supabase, OpenAI, Lemon Squeezy keys

bash infra/scripts/deploy.sh
```

GitHub Actions auto-deploys on push to `main` once you set repository secrets:

- `HETZNER_HOST` — your VPS IP
- `HETZNER_USER` — SSH user (typically `deploy`)
- `HETZNER_SSH_KEY` — private key for that user

#### Web on Cloudflare Pages

1. Create Cloudflare account (free)
2. Pages → "Create a project" → "Connect to Git" → select your repo
3. Build settings:
   - Build command: `pnpm install && pnpm --filter @scalemyprints/web build`
   - Build output directory: `apps/web/.next`
   - Root directory: `/`
4. Environment variables (production):
   - `NEXT_PUBLIC_APP_URL=https://scalemyprints.com`
   - `NEXT_PUBLIC_API_URL=https://api.scalemyprints.com`
   - `NEXT_PUBLIC_SUPABASE_URL=...`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY=...`
5. Custom domain: `scalemyprints.com` → CNAME

#### Workers domain (api.scalemyprints.com)

1. In Cloudflare DNS, add `A` record `api` → Hetzner IP, proxy ON
2. Add origin certificate or use Cloudflare flexible SSL
3. Test: `curl https://api.scalemyprints.com/health`

#### Supabase migrations

```bash
cd infra/supabase
supabase link --project-ref <your-prod-ref>
supabase db push
```

Verify the trigger fires by signing up a test user and checking:

```sql
SELECT * FROM users_profile WHERE id = '<test-user-id>';
SELECT * FROM subscriptions WHERE user_id = '<test-user-id>';
SELECT * FROM usage_limits WHERE user_id = '<test-user-id>';
```

All three should have rows.

### Cost ceiling per user

| Service       | Free tier ceiling | Cost beyond                |
| ------------- | ----------------- | -------------------------- |
| Supabase      | 500MB DB, 50k MAU | $25/mo for 8GB             |
| Cloudflare Pages | unlimited      | $0                         |
| Hetzner CX11  | €4/mo flat        | upgrade to CX21 at €6/mo   |
| Resend        | 3k emails/mo      | $20/mo for 50k emails      |
| OpenAI        | pay per request   | ~$0.001 per trademark check |
| Lemon Squeezy | 5% per transaction | flat fee                   |

At 100 paying users on Pro Bundle ($149/mo), gross revenue is $14,900/mo and infrastructure is ~$50/mo. Plenty of room.

## Phase E: LLC + scale

Trigger this when MRR ≥ $5,000 and tax/legal complexity warrants:

| Item                                     | Cost      |
| ---------------------------------------- | --------- |
| Stripe Atlas LLC formation (Delaware)    | $500      |
| Annual registered agent                  | $50       |
| First-year compliance                    | $20       |
| **Total**                                | **~$571** |

After incorporation, you can:

- Switch payment processor to Stripe directly (lower fees than Lemon Squeezy)
- Open a US business bank account
- Sign B2B contracts (agency clients)

## Disaster recovery

| What breaks            | Detection                          | Recovery                                  |
| ---------------------- | ---------------------------------- | ----------------------------------------- |
| Workers VPS down       | Cloudflare → 521; Sentry alert     | `bash infra/scripts/deploy.sh` rebuilds   |
| Supabase outage        | Status page; failing health checks | Wait — managed service                    |
| USPTO API down         | Per-jurisdiction error in response | Graceful degradation built-in             |
| Bad deploy             | CI fails before deploy             | If past CI: `git revert HEAD && git push` |
| Lost SSH key           | Can't deploy                       | Add new key via Hetzner web console       |

Daily Supabase backups are automatic on the free tier (7-day retention).

## Monitoring checklist

After Phase D launch, verify daily for the first week:

- [ ] Sentry — zero unresolved errors
- [ ] Supabase dashboard — DB size growing reasonably
- [ ] PostHog funnel — signup → first search conversion
- [ ] Hetzner — CPU < 50%, memory < 70%
- [ ] Lemon Squeezy — subscriptions matching expected revenue
- [ ] Logs — no auth errors, no rate-limit storms from a single IP
