# Restaurant Reservation Monitor

A tiny app that watches **Resy / OpenTable / Tock / Yelp / Wisely** for
reservation openings at the restaurants and times you care about, and texts
you a tap-to-book link the moment a slot appears. Runs on GitHub Actions, so
your laptop can be closed.

It does **not** auto-book. That avoids TOS violations, account bans, stored
passwords, and stored credit cards. In practice, getting an SMS the instant a
slot opens and tapping a deep link is about as fast as auto-booking — and far
more reliable.

## How it works

1. GitHub Actions runs `src/main.py` on a 5-minute cron (the platform minimum).
2. Inside each run, the script polls **3 times with a 2-min sleep between**
   — so you get ~2-min effective polling without fighting GitHub's cron limit.
3. For each entry in `restaurants.yaml`, each poll queries the platform's
   public availability endpoint.
4. If a slot inside your time window has opened and you haven't already been
   notified about it, it sends you an SMS via Twilio with a deep link that
   drops you straight onto the booking page with date / time / party-size
   pre-filled.
5. Sent alerts are recorded in `state.json` (committed back by the workflow)
   so you don't get the same SMS twice.

### Cost & GitHub Actions free tier (important)

- **Twilio:** ~$1.15/mo for the phone number + ~$0.008 per SMS sent.
- **GitHub Actions on a public repo:** unlimited and free.
- **GitHub Actions on a private repo:** free tier is 2,000 min/month. With
  ~5-min runs (3 polls × 2 min sleep + overhead) every 5 min, you'd burn
  ~7,200 min/month — far over the limit.

**TL;DR: make the repo public.** Your secrets (Twilio creds, your phone
number) are stored in encrypted GitHub Secrets, *not* in code, so making the
repo public is safe. The only thing visible would be `restaurants.yaml`,
which is not sensitive.

Alternatives if you want it private: GitHub Pro ($4/mo, 3,000 min — still
tight), or port the script to Cloudflare Workers (free, true 1-min polling,
but the Python has to be rewritten in JS).

## Setup (one-time, ~15 min)

### 1. Push this code to a private GitHub repo
```bash
cd restaurant-sniper
git init
git add .
git commit -m "Initial commit"
gh repo create restaurant-sniper --private --source=. --push
# or create the repo in the GitHub UI and push manually
```

### 2. Sign up for Twilio
- Create an account at https://twilio.com (trial works for testing).
- Buy a phone number with SMS capability (~$1.15/mo).
- From the Twilio console, copy your **Account SID**, **Auth Token**, and
  the **phone number** you bought (in E.164 format, e.g. `+15551234567`).

### 3. Add GitHub secrets
In your repo on github.com, go to **Settings → Secrets and variables → Actions
→ New repository secret** and add four secrets:

| Name | Value |
|---|---|
| `TWILIO_ACCOUNT_SID` | Your Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Your Twilio auth token |
| `TWILIO_FROM` | Your Twilio phone number, e.g. `+15551234567` |
| `NOTIFY_TO` | Your personal phone number, e.g. `+15555550123` |

### 4. Edit `restaurants.yaml`
Add an entry per restaurant + date + time window. See the
[Finding venue IDs](#finding-venue-ids) section below for how to get the right
ID per platform.

### 5. Test with a dry run
In the **Actions** tab on GitHub, pick **Restaurant Reservation Monitor**,
click **Run workflow**, set `dry_run` to `true`, and run it. Open the run logs
and look for lines like:

```
[resy] Din Tai Fung — Century City on 2026-05-03: 12 slot(s) returned
```

If you see slot counts, the adapter is talking to the platform correctly. If
you see `0 slot(s)`, that just means nothing is available right now (which is
the whole point of this app).

If a slot is currently open inside your window, you'll see a `MATCH:` line in
the logs and — when you turn dry-run off — an SMS will fire.

### 6. Enable the cron
The workflow runs automatically every 5 minutes once it's on the default
branch. To pause it, disable the workflow in the Actions tab.

## Finding venue IDs

### Resy
1. Open the restaurant page on resy.com (e.g.
   `https://resy.com/cities/la/din-tai-fung`).
2. Open Chrome DevTools → Network → reload.
3. Look for a request to `api.resy.com/3/venue/search` or `api.resy.com/4/find`.
   The response contains `"id": <number>` — that's your `venue_id`.
4. The URL slug (`din-tai-fung` in the example above) is your `venue_slug`,
   and the city code (`la`) is your `city_code`.

### OpenTable
1. Open the restaurant page on opentable.com.
2. The URL contains `/r/<slug>` — open DevTools → Network and look at one of
   the API calls. The numeric `restaurantId` (also called `rid`) is your
   `venue_id`.

### Tock
1. Open the restaurant on exploretock.com — the URL slug
   (`exploretock.com/<slug>`) is your `venue_id`.

### Yelp Reservations
1. Open the restaurant's reservation page on yelp.com (e.g.
   `https://www.yelp.com/reservations/din-tai-fung-glendale-2`).
2. The slug after `/reservations/` is your `venue_id` (e.g.
   `din-tai-fung-glendale-2`).
3. Note: Yelp doesn't publish an availability API. The adapter tries a JSON
   endpoint and falls back to scraping embedded data from the HTML. If you
   see `0 slot(s)` returned when slots clearly exist in a browser, open
   Chrome DevTools → Network on the Yelp reservation page, look at the
   request that loads the time picker, and update
   `src/adapters/yelp.py:_try_json_endpoint` to match.

### Wisely / Olo Engage
Wisely doesn't have one central API — each restaurant embeds the Wisely
booking widget on its own website. So you have to find the specific
availability URL for *your* restaurant:

1. Open the restaurant's reservation page (the page with the date/time picker).
2. Open Chrome DevTools → **Network** tab → filter by "Fetch/XHR".
3. Pick a date and party size in the widget. Watch for a request that
   returns JSON containing time slots — usually a URL with `availability`,
   `times`, or `openings` in the path.
4. Right-click that request → **Copy → Copy as cURL**. Look at the URL.
5. In `restaurants.yaml`, set `availability_url` to that URL, replacing the
   date / party-size / venue-id segments with the placeholders `{date}`,
   `{party_size}`, `{venue_id}`. Example:

   ```yaml
   - name: "Some Restaurant"
     platform: wisely
     venue_id: "12345"
     party_size: 2
     date: "2026-05-10"
     time_window: ["19:00", "20:00"]
     availability_url: "https://book.example.com/api/v1/availability/{venue_id}?date={date}&size={party_size}"
     reservation_page_url: "https://www.example.com/reservations"
   ```

6. If the request is a POST with a JSON body, set
   `availability_method: "POST"` and put the body shape under
   `availability_body:` with the same `{...}` placeholders inside string values.
7. Run a dry-run (Actions → Run workflow → `dry_run: true`) and check that
   slot counts come back.

## Config reference

```yaml
watches:
  - name: "Friendly label for SMS"   # required
    platform: resy                   # resy | opentable | tock — required
    venue_id: "12345"                # required
    venue_slug: "din-tai-fung"       # Resy only — used for booking link
    city_code: "la"                  # Resy only — used for booking link
    party_size: 2                    # required
    date: "2026-05-03"               # YYYY-MM-DD, "today", or "tomorrow"
    time_window: ["18:00", "18:45"]  # 24h HH:MM, inclusive
    booking_url: "..."               # optional — overrides the default link.
                                     # Placeholders: {date} {party_size}
                                     # {time} {time_compact}
```

## Polling cadence

Default config: cron every 5 min, 3 polls per run with 2-min sleep between.
Effective polling: ~2 min.

Tune via env vars on the workflow (`.github/workflows/monitor.yml`):
- `LOOP_COUNT` — polls per run (default 3)
- `LOOP_INTERVAL_SEC` — seconds between polls (default 120)

A few sane combos:
- `LOOP_COUNT=3 LOOP_INTERVAL_SEC=120` → ~2-min polling (default, current)
- `LOOP_COUNT=5 LOOP_INTERVAL_SEC=60` → ~1-min polling (uses ~5 min per run,
  same Actions cost)
- `LOOP_COUNT=1 LOOP_INTERVAL_SEC=0` → simple 5-min polling (cheapest)

## Limitations & notes

- **GitHub Actions cron is best-effort.** Runs are scheduled every 5 min but
  can be delayed by 5–15 minutes during peak load. For ultra-hot
  reservations where seconds matter, port the monitor to **Cloudflare
  Workers** (free tier, 1-minute cron) — the adapter code is identical.
- **OpenTable can change endpoints without notice.** If `0 slot(s)` keeps
  coming back when you can clearly see availability in a browser, open
  DevTools on the OpenTable booking widget and update
  `src/adapters/opentable.py` to match the new payload shape.
- **You'll get one SMS per (slot, time, date) combination.** The state file
  dedupes so reruns of the same cron don't re-text you about the same 6:30pm
  slot. If a slot disappears and reappears later, you'll get a second SMS
  (which is what you want).
- **No financial / credentials are stored anywhere.** This app reads public
  availability only. You complete the booking yourself in the Resy /
  OpenTable / Tock app on your phone, where you're already logged in.
- **Don't set the cron faster than every 5 min on Resy/OpenTable.** They
  watch for abusive request patterns. 5-minute intervals from a single IP
  are fine.

## Adding more platforms

Add a new file in `src/adapters/` that subclasses `Adapter` and implements
`find_slots(...)`, then register it in `src/adapters/__init__.py`. The
`Slot` dataclass is the contract — return a list of those.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Dry run (prints what would have been texted)
DRY_RUN=1 python -m src.main

# Real run (uses your env vars)
TWILIO_ACCOUNT_SID=... TWILIO_AUTH_TOKEN=... \
TWILIO_FROM=+15551234567 NOTIFY_TO=+15555550123 \
python -m src.main
```
