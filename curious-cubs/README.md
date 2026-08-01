# Curious Cubs Webinar — Website + Admin

One Next.js app with two faces:

| Surface | URL | What it does |
|---|---|---|
| **Website** | `/` | Curious Cubs webinar landing page: hero, live schedule, contact form |
| **Admin** | `/admin` | Password-protected panel: manage the webinar calendar + read enquiries |

The two are connected through a shared store — when the admin adds/edits/deletes
a session, the website updates instantly (the site is server-rendered per
request and the schedule also auto-refreshes in the browser every 30s).
Contact-form submissions are emailed to **dev@sorsco.in** and also saved so
they're always visible in the admin panel under **Enquiries**.

## Run locally

```bash
cd curious-cubs
npm install
cp .env.example .env   # optional — sensible defaults are built in
npm run dev            # http://localhost:3000  (admin: /admin)
```

Default admin password: `curiouscubs@2026` (set `ADMIN_PASSWORD` to change it).
Locally, data lives in `.data/db.json` — no database needed.

## Deploy on Vercel

1. Push this repo to GitHub (already done if you're reading this on GitHub).
2. In [Vercel](https://vercel.com/new): **Import** the repository.
   - Set **Root Directory** to `curious-cubs`.
   - Framework is auto-detected (Next.js). Deploy.
3. **Storage** (so calendar data survives redeploys):
   - Vercel dashboard → your project → **Storage** → **Upstash Redis**
     (free tier) → Connect. The `KV_REST_API_URL` / `KV_REST_API_TOKEN`
     env vars are injected automatically. Redeploy once after connecting.
4. **Email** (contact form → dev@sorsco.in):
   - Create a free account at [resend.com](https://resend.com) → API Keys →
     create a key.
   - Vercel → project → **Settings → Environment Variables**:
     - `RESEND_API_KEY` = the key
     - `CONTACT_TO_EMAIL` = `dev@sorsco.in`
     - `ADMIN_PASSWORD` = a strong password of your choice
   - Redeploy. (Note: on Resend's free tier without a verified domain, the
     recipient must be the email you signed up to Resend with — sign up with
     dev@sorsco.in, or verify the sorsco.in domain in Resend and set
     `CONTACT_FROM_EMAIL` to e.g. `Curious Cubs <hello@sorsco.in>`.)

Without Redis the app still works, but data is stored in `/tmp` on the
serverless function — fine for a quick demo, lost on redeploy (the admin
panel shows a warning banner in that state).
Without a Resend key the contact form still works — submissions are saved and
shown in **Admin → Enquiries**, just not emailed.

## Environment variables

See [.env.example](.env.example) for the full list with comments.

| Var | Purpose | Default |
|---|---|---|
| `ADMIN_PASSWORD` | /admin login | `curiouscubs@2026` |
| `RESEND_API_KEY` | send contact emails | _(unset → store only)_ |
| `CONTACT_TO_EMAIL` | enquiry recipient | `dev@sorsco.in` |
| `CONTACT_FROM_EMAIL` | sender identity | `Curious Cubs <onboarding@resend.dev>` |
| `UPSTASH_REDIS_REST_URL/TOKEN` or `KV_REST_API_URL/TOKEN` | persistent storage | _(unset → JSON file)_ |

## How the sync works

- Sessions live in one store (`lib/store.ts`): Upstash Redis when configured,
  else a JSON file.
- Admin CRUD goes through `/api/admin/sessions*` (cookie-authenticated).
- The website reads the same store server-side on every request
  (`force-dynamic`) and the `<Schedule>` component re-fetches
  `/api/sessions` every 30 seconds, so an open browser tab picks up admin
  changes without a reload.

## Project layout

```
app/page.tsx                      # public website
app/admin/page.tsx                # admin panel (login + calendar + enquiries)
app/api/sessions/route.ts         # public: list sessions
app/api/contact/route.ts          # public: submit contact form (emails + stores)
app/api/admin/login|logout        # admin auth (signed HttpOnly cookie)
app/api/admin/sessions[/id]       # admin: create / update / delete sessions
app/api/admin/contacts            # admin: list enquiries
lib/store.ts                      # Redis-or-file storage layer
lib/auth.ts                       # password check + HMAC-signed session cookie
lib/email.ts                      # Resend email sender
```
