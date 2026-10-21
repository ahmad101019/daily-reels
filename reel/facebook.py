"""Publishes a Reel to a Facebook Page via the Graph API (video_reels)."""
import os
import time

import requests


class FBError(RuntimeError):
    pass


def _check(r, step):
    try:
        data = r.json()
    except ValueError:
        data = {"raw": r.text[:500]}
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", data)
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        hint = ""
        if isinstance(err, dict) and err.get("code") == 190:
            hint = " -> Page token expired/invalid. Generate a new long-lived Page token and update FB_PAGE_TOKEN."
        elif isinstance(err, dict) and err.get("code") in (10, 200):
            hint = " -> Missing permission. Token needs pages_manage_posts, pages_read_engagement, pages_show_list."
        raise FBError(f"[{step}] HTTP {r.status_code}: {msg}{hint}")
    return data


def post_reel(page_id, token, video_path, description, api_version="v23.0"):
    base = f"https://graph.facebook.com/{api_version}"

    # 1) start upload session
    start = _check(requests.post(f"{base}/{page_id}/video_reels",
                                 data={"upload_phase": "start", "access_token": token}, timeout=60), "start")
    video_id = start["video_id"]
    upload_url = start.get("upload_url", f"https://rupload.facebook.com/video-upload/{api_version}/{video_id}")

    # 2) upload bytes
    size = os.path.getsize(video_path)
    with open(video_path, "rb") as fh:
        up = _check(requests.post(upload_url, data=fh, timeout=900, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)}), "upload")
    if not up.get("success", True):
        raise FBError(f"[upload] {up}")

    # 3) publish
    _check(requests.post(f"{base}/{page_id}/video_reels", timeout=60, data={
        "access_token": token, "video_id": video_id, "upload_phase": "finish",
        "video_state": "PUBLISHED", "description": description}), "finish")

    # 4) wait for processing/publishing to complete
    deadline = time.time() + 15 * 60
    last = {}
    while time.time() < deadline:
        st = _check(requests.get(f"{base}/{video_id}", timeout=60,
                                 params={"fields": "status", "access_token": token}), "status")["status"]
        last = st
        vs = st.get("video_status")
        if vs == "error" or any(st.get(p, {}).get("status") == "error"
                                for p in ("uploading_phase", "processing_phase", "publishing_phase")):
            raise FBError(f"[status] Facebook rejected the video: {st}")
        if st.get("publishing_phase", {}).get("status") == "complete" or vs in ("ready", "published"):
            return video_id
        time.sleep(15)
    print(f"Warning: still processing after 15 min, last status {last}. It will usually publish on its own.")
    return video_id
