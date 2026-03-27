# family-briefing-bot

Standalone scheduler project for:
- Composing the household daily report every 4 hours.
- Sending the daily report at 05:30 (local machine time).
- Sending appointment reminders every 5 minutes. Telegram defaults to 90/45/15 minutes before start; email defaults to 90 minutes only.
- Writing both Markdown and HTML daily reports.

This repo is intentionally independent from Agent Zero custom scheduler tasks.

## Runtime

- Python: `~/common_env/bin/python`
- Secrets/env: loaded from `config/settings.json` -> `env_files`
- Google OAuth token: configured in `config/settings.json` (`google.google_creds_path`)

## Setup

```bash
cd family-briefing-bot
~/common_env/bin/python -m pip install -r requirements.txt
```

## Configure

Create local config from examples:

```bash
cp config/settings.example.json config/settings.json
cp .env.example .env
```

Then edit:
- `config/settings.json`
- `.env` (or another file listed in `env_files`)

Important values:
- `daily_report.telegram_chat_ids`
- `daily_report.email_recipients`
- `reminders.*`
- `google.google_creds_path` (absolute path to authorized user JSON)
- `daily_report.header_image_path`
- `daily_report.close_line_source` (`online` or `local`)
- `env_files` (where `TELEGRAM_BOT_TOKEN` and weather API key are sourced)

Recommended durable setup (multi-project, multi-account):
- Keep each project's OAuth credentials in a dedicated identity file.
- Set `google.google_creds_path` in `config/settings.json` to the full absolute path.
- Never share one token file path across multiple projects/accounts.

## Header image customization (single-repo workflow)

- Git-tracked default header: `static/daily_report.png` (generic/public-safe).
- Local personal header: put your private image at `static/local/daily_report.png`.
- Set `daily_report.header_image_path` in your local `config/settings.json` to:
  - `static/local/daily_report.png`

`static/local/*` is gitignored, so your personal image will never be pushed.

## Google setup

This app needs:
- Google Calendar API (read events)
- Gmail API (send emails)
- Google Weather API (daily forecast)

1. Create a Google Cloud project.
2. Enable `Google Calendar API`, `Gmail API`, and `Weather API`.
3. Configure OAuth consent screen and add your account as a test user (if app is in testing).
4. Create an OAuth client (`Desktop app` is simplest).
5. Generate a token JSON that includes scopes:
   - `https://www.googleapis.com/auth/calendar`
   - `https://www.googleapis.com/auth/gmail.modify`
6. Put that authorized user JSON file somewhere stable and set:
   - `config/settings.json`: `google.google_creds_path=/absolute/path/to/google-authorized-user.json`
7. Add a weather key to one of your `env_files` using one of:
   - `GOOGLE_MAPS_KEY=...`
   - `GOOGLE_MAPS_API_KEY=...`
   - `GOOGLE_API_KEY=...`
   - `MAPS_API_KEY=...`

## Telegram setup

1. Create a bot with `@BotFather` and copy the bot token.
2. Add `TELEGRAM_BOT_TOKEN=...` to one of the files listed in `env_files`.
3. Send at least one message to your bot from each Telegram account that should receive reports.
4. Find chat IDs:
   - `curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates"`
   - Copy each numeric `chat.id` value.
5. Set chat IDs in `config/settings.json`:
   - `daily_report.telegram_chat_ids`
   - `reminders.always_telegram_chat_ids`
   - `reminders.owner_telegram_chat_ids`

## Manual runs

```bash
cd family-briefing-bot
~/common_env/bin/python scripts/generate_daily_report.py
~/common_env/bin/python scripts/send_daily_report.py
~/common_env/bin/python scripts/send_appointment_reminders.py
~/common_env/bin/python scripts/capture_google_weather_sample.py
```

## launchd install

```bash
cd family-briefing-bot
bash launchd/install_launchd.sh
```

To remove jobs:

```bash
bash launchd/uninstall_launchd.sh
```

To check status/logs:

```bash
bash launchd/status.sh
```

## Notes

- launchd schedules use macOS local timezone.
- Reminder timing is channel-aware:
  - `reminders.offsets_minutes` controls Telegram reminder offsets.
  - `reminders.email_offsets_minutes` controls email reminder offsets and defaults to `[90]`.
- If a token expires and cannot refresh, rerun OAuth in the project that owns your Google credentials/token.
- Google Weather daily forecasts can include a pre-midnight carryover day in early runs. The report logic normalizes weather to local `timezone` midnight and always renders `today + next 2 days`.
