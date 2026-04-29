# Known Issues

Issues identified during local development that will be addressed in Phase B (production deploy + beta validation).

---

## 🔴 Issue #1: JWT Token Not Reaching Workers from Web Frontend

**Symptom:** Logged-in users on web dashboard make trademark search requests, but workers logs show `anonymous=True` instead of the real user_id.

**Diagnosis:**
- Workers receives the request
- Workers does NOT see the `Authorization: Bearer <jwt>` header
- `jwt_invalid` warning never fires (auth code path not entered)
- Even with explicit fake token in curl, no warning appears

**Likely Root Cause:**
Frontend `api-client.ts` calls `getSession()` from Supabase, which may return `null` even when user is authenticated, OR the token attachment logic has a bug.

**Impact:**
- Anonymous flows work fine (Chrome extension free tier, public marketing)
- Logged-in user search history won't persist correctly per-user
- Per-user rate limits won't apply

**Workaround for Phase A:**
- Anonymous flows are sufficient for beta validation
- Search history persistence is also pending (see Issue #4)

**Phase B Fix Plan:**
1. Add browser DevTools `Authorization` header inspection
2. Add console.log in `api-client.ts` `getAuthToken()` to confirm token retrieval
3. Verify `apps/web/.env.local` `NEXT_PUBLIC_SUPABASE_URL` matches `apps/workers/.env` `SUPABASE_URL`
4. Test in production (Cloudflare Pages → Hetzner) — may resolve due to clean session state

**Files to investigate:**
- `apps/web/src/lib/api-client.ts` — `getAuthToken()` function
- `apps/web/src/lib/supabase/client.ts` — `createSupabaseBrowserClient()`
- `apps/workers/src/scalemyprints/api/middleware/auth.py` — `get_current_user_or_anonymous()`

---

## 🔴 Issue #2: US Adapter (Marker API) Network Unreachable from Bangladesh

**Symptom:** Marker API requests fail with `httpx.ConnectError`. Repeats 3 retry attempts before giving up.

**Logs:**
```
[error] marker_search_unexpected_error
httpcore.ConnectError → httpx.ConnectError
```

**Likely Root Cause:**
Bangladesh ISP firewall or geo-blocking preventing TLS handshake to `markerapi.com`.

**Impact:**
- US jurisdiction returns "unexpected:ConnectError" instead of real data
- AU still works (different geo path)

**Workaround for Phase A:**
- Beta launch with AU jurisdiction prominently working
- Show US/EU as "Coming Soon" in UI (or fail gracefully — already implemented)

**Phase B Fix Plan:**
1. Test from production Hetzner VPS (US/EU server) — likely works
2. If still broken, switch to alternative US data source (USPTO direct with API key, or alternative aggregator)
3. Implement provider fallback chain

---

## 🔴 Issue #3: EU Adapter (TMView) Network Unreachable from Bangladesh

**Symptom:** Identical to Issue #2 but for `tmview.tmdn.org`.

**Logs:**
```
[error] tmview_search_unexpected_error
httpcore.ReadError → httpx.ReadError
```

**Likely Root Cause:** Same as Issue #2 — Bangladesh network blocking.

**Phase B Fix Plan:** Same as Issue #2 — verify on production server.

---

## 🟡 Issue #4: Search History Not Persisting to Database

**Symptom:** `tm_searches` table remains empty even after authenticated users search.

**Root Cause:** Not a bug — feature intentionally deferred. Database table exists with correct schema, but `apps/workers/src/scalemyprints/api/routes/trademark.py` doesn't include the Supabase save call yet.

**Impact:**
- Users can't view their search history
- No analytics on search patterns

**Phase B Fix Plan:**
1. Add Supabase client wrapper: `infrastructure/storage/search_history.py`
2. After successful search in route, call `await save_search(user_id, request, response)`
3. Add `/api/v1/trademark/history` endpoint to retrieve user's past searches
4. Frontend page at `/dashboard/history`

**Estimated Effort:** ~25 minutes coding + tests

---

## 🟢 Resolved Issues (Phase A)

- ✅ Pydantic v2 generic syntax for `ApiSuccess[T]` (fixed in Phase 5)
- ✅ Date normalizer accepting invalid dates like `2024-13-45` (fixed in Phase 4)
- ✅ Unicode regex requiring `regex` library (changed to ASCII-only in Phase 3)
- ✅ Multi-class deduplication test setup (fixed in Phase 4)
- ✅ Multi-provider Container wiring (fixed in this session)

---

## 📋 Phase B Pre-Launch Checklist

Before inviting first beta users:

- [ ] Resolve Issue #1 (JWT token attachment)
- [ ] Verify Issue #2 + #3 on production server
- [ ] Implement Issue #4 (search history persistence)
- [ ] Add `/dashboard/history` page
- [ ] Production deploy:
  - [ ] Hetzner CX11 VPS provisioned
  - [ ] Cloudflare Pages connected to repo
  - [ ] DNS configured (`scalemyprints.com` → CF, `api.scalemyprints.com` → Hetzner)
  - [ ] HTTPS certs verified
  - [ ] Production Supabase project (separate from dev)
  - [ ] Resend account for transactional email
- [ ] End-to-end smoke test on production
- [ ] First 5 beta users selected and contacted
