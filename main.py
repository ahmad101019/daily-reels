"""Daily reel: pick today's script -> render video + voiceover -> post at 9 PM PKT."""
import csv
import datetime as dt
import json
import os
import sys
import time

from reel import facebook, render

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)


def env_true(name):
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def pick_script(scripts, cfg, today):
    if os.getenv("SCRIPT_INDEX", "").strip():
        i = int(os.environ["SCRIPT_INDEX"]) % len(scripts)
    else:
        start = dt.date.fromisoformat(cfg["start_date"])
        i = (today - start).days % len(scripts)
    return i, scripts[i]


def wait_until_post_time(cfg):
    hh, mm = map(int, cfg["post_time_utc"].split(":"))
    now = dt.datetime.now(dt.timezone.utc)
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    wait = (target - now).total_seconds()
    if 0 < wait <= 60 * 60:
        print(f"Reel ready. Waiting {int(wait // 60)} min to post at {cfg['post_time_utc']} UTC (9:00 PM PKT)...")
        time.sleep(wait)


def main():
    cfg = json.load(open("config.json"))
    scripts = json.load(open("content/scripts.json"))
    dry_run = env_true("DRY_RUN")
    pkt_today = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5)).date()

    idx, script = pick_script(scripts, cfg, pkt_today)
    print(f"Script #{idx}: {render.plain(script['hook'])}")

    video, seconds = render.build(script, "out", cfg, silent=env_true("SILENT_AUDIO"))
    print(f"Rendered {video} ({seconds:.1f}s)")

    if dry_run:
        print("DRY RUN: not posting. Download the video from this run's artifacts.")
        return

    page_id, token = os.getenv("FB_PAGE_ID"), os.getenv("FB_PAGE_TOKEN")
    if not page_id or not token:
        sys.exit("Missing FB_PAGE_ID / FB_PAGE_TOKEN repository secrets.")

    if not env_true("POST_NOW"):
        wait_until_post_time(cfg)

    vid = facebook.post_reel(page_id, token, video, script["caption"], cfg["graph_api_version"])
    print(f"Posted reel, video id {vid}")

    os.makedirs("log", exist_ok=True)
    new = not os.path.exists("log/posted.csv")
    with open("log/posted.csv", "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["date_pkt", "script_index", "hook", "video_id"])
        w.writerow([pkt_today.isoformat(), idx, render.plain(script["hook"]), vid])


if __name__ == "__main__":
    main()
