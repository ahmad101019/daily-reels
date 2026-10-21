# Daily Reels

Posts one animated-text Reel with an AI voiceover to the Facebook Page **Ahmad Faraz Khan Balouch** every day at **9:00 PM PKT**. Fully automatic, 100% free (GitHub Actions + free Microsoft neural TTS + Facebook Graph API). No Zapier tasks used.

## How it works
1. GitHub Actions starts at ~8:17 PM PKT.
2. Picks today's script from `content/scripts.json` (30 scripts, rotates daily).
3. Generates the voiceover, renders a 1080x1920 video with word-by-word animated text.
4. Waits until 9:00 PM PKT and publishes it as a Reel.
5. Logs it in `log/posted.csv`.

## One-time setup (2 secrets)
Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|---|---|
| `FB_PAGE_ID` | Your Page ID (Page → About → Page transparency, or from step 4 below) |
| `FB_PAGE_TOKEN` | Long-lived Page access token (steps below) |

### Get a never-expiring Page token
1. Go to developers.facebook.com → **My Apps → Create App** → type **Business**.
2. Open **Tools → Graph API Explorer**, select your app.
3. Add permissions: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts` → **Generate Access Token** → approve for your Page.
4. Make it long-lived: open **Tools → Access Token Debugger**, paste the token → **Extend Access Token**. Copy the new token.
5. Back in Graph API Explorer, paste that long-lived token, run `GET me/accounts`. Copy your Page's `access_token` and `id`.
   That Page token does not expire. Use it for `FB_PAGE_TOKEN`, and the `id` for `FB_PAGE_ID`.

## Test it
**Actions → Daily Reel → Run workflow**
- `dry_run` ON → builds the video only. Download it from the run's **Artifacts**.
- `dry_run` OFF + `post_now` ON → posts immediately (good first live test).

## Customize
- Scripts: edit `content/scripts.json`. Wrap a word in `*stars*` to highlight it in gold.
- Voice, colors, CTA, post time: `config.json` (`post_time_utc` 16:00 = 9 PM PKT).
- Voices to try: `en-US-AndrewNeural`, `en-US-GuyNeural`, `en-GB-RyanNeural`.
