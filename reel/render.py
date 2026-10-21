"""Builds a 1080x1920 animated-text reel with an AI voiceover."""
import asyncio
import math
import os
import re
import subprocess
import wave

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
MARGIN = 96
SCENE_PAD = 0.35  # silence after each spoken line (seconds)

FONT_CANDIDATES = [
    "fonts/Montserrat-ExtraBold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def _hex(c, a=255):
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), a)


def plain(text):
    return text.replace("*", "")


# ---------- audio ----------

async def _tts(text, voice, rate, out):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(out)


def _run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _scene_audio(text, idx, workdir, cfg, silent):
    wav = os.path.join(workdir, f"scene{idx}.wav")
    if silent:  # local testing only: estimate speaking time
        dur = max(1.6, len(plain(text).split()) * 0.38)
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
              "-t", f"{dur + SCENE_PAD:.2f}", wav])
        return wav
    mp3 = os.path.join(workdir, f"scene{idx}.mp3")
    for attempt in range(3):
        try:
            asyncio.run(_tts(plain(text), cfg["voice"], cfg["voice_rate"], mp3))
            if os.path.getsize(mp3) > 0:
                break
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise RuntimeError(f"Voiceover failed: {e}") from e
    _run(["ffmpeg", "-y", "-i", mp3, "-af", f"apad=pad_dur={SCENE_PAD}",
          "-ar", "44100", "-ac", "2", wav])
    return wav


def _wav_dur(path):
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def _concat_wavs(paths, out):
    with wave.open(paths[0]) as first:
        params = first.getparams()
    with wave.open(out, "wb") as o:
        o.setparams(params)
        for p in paths:
            with wave.open(p) as w:
                o.writeframes(w.readframes(w.getnframes()))


# ---------- visuals ----------

def _background(cfg):
    top, bot = _hex(cfg["colors"]["bg_top"]), _hex(cfg["colors"]["bg_bottom"])
    grad = Image.new("RGBA", (1, H))
    for y in range(H):
        t = y / (H - 1)
        grad.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,))
    return grad.resize((W, H))


def _glow(color, size, alpha):
    g = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse((size * 0.2, size * 0.2, size * 0.8, size * 0.8), fill=_hex(color, alpha))
    return g.filter(ImageFilter.GaussianBlur(size * 0.14))


def _tokens(text):
    """Split into (word, highlighted) pairs; *word* marks accent words."""
    out, hl = [], False
    for part in re.split(r"(\*)", text):
        if part == "*":
            hl = not hl
            continue
        for j, w in enumerate(part.split()):
            glue = j == 0 and out and not part[:1].isspace() and not re.match(r"\w", w)
            out.append((w, hl, bool(glue)))
    return out


def _layout(tokens, font, max_w, draw):
    lines, cur, cur_w = [], [], 0
    space = draw.textlength(" ", font=font)
    for w, hl, glue in tokens:
        ww = draw.textlength(w, font=font)
        sp = 0 if (glue or not cur) else space
        if cur and not glue and cur_w + sp + ww > max_w:
            lines.append(cur)
            cur, cur_w, sp = [], 0, 0
        cur.append((w, hl, ww, sp))
        cur_w += sp + ww
    if cur:
        lines.append(cur)
    return lines, space


def _ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def build(script, workdir, cfg, silent=False):
    os.makedirs(workdir, exist_ok=True)
    scenes = [script["hook"]] + script["lines"] + [cfg["cta"]]

    wavs = [_scene_audio(s, i, workdir, cfg, silent) for i, s in enumerate(scenes)]
    durs = [_wav_dur(w) for w in wavs]
    audio = os.path.join(workdir, "voice.wav")
    _concat_wavs(wavs, audio)
    total = sum(durs)

    col = cfg["colors"]
    bg = _background(cfg)
    glow_a = _glow(col["accent"], 1100, 70)
    glow_b = _glow(col["accent2"], 1000, 55)
    scratch = ImageDraw.Draw(Image.new("RGBA", (10, 10)))

    label_font = _font(34)
    tag_font = _font(26)
    handle_font = _font(32)

    # pre-layout every scene
    laid = []
    for i, s in enumerate(scenes):
        size = 112 if i == 0 else 92
        font = _font(size)
        lines, space = _layout(_tokens(s), font, W - 2 * MARGIN, scratch)
        while len(lines) > 6 and size > 56:
            size -= 6
            font = _font(size)
            lines, space = _layout(_tokens(s), font, W - 2 * MARGIN, scratch)
        laid.append((font, lines, space, int(size * 1.28)))

    out = os.path.join(workdir, "reel.mp4")
    ff_log = open(os.path.join(workdir, "ffmpeg.log"), "w+")
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", audio, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest",
         "-movflags", "+faststart", out],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=ff_log)

    starts = [sum(durs[:i]) for i in range(len(durs))]
    n_frames = int(math.ceil(total * FPS))
    text_col, accent, muted = _hex(col["text"]), _hex(col["accent"]), _hex(col["muted"])

    for f in range(n_frames):
        t = f / FPS
        si = max(i for i in range(len(starts)) if starts[i] <= t + 1e-9)
        lt, dur = t - starts[si], durs[si]
        font, lines, space, lh = laid[si]

        frame = bg.copy()
        frame.alpha_composite(glow_a, (int(-300 + 220 * math.sin(t * 0.35)), int(200 + 160 * math.cos(t * 0.27))))
        frame.alpha_composite(glow_b, (int(450 + 200 * math.cos(t * 0.31)), int(1050 + 180 * math.sin(t * 0.23))))

        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        # header
        d.text((MARGIN, 150), cfg["brand_label"], font=label_font, fill=accent)
        d.text((MARGIN, 200), cfg["brand_tagline"], font=tag_font, fill=muted)
        d.rectangle((MARGIN, 250, MARGIN + 90, 256), fill=accent)

        # words reveal one by one, whole block fades out at scene end
        n_words = sum(len(l) for l in lines)
        reveal = min(dur * 0.55, 0.16 * n_words + 0.2)
        fade_out = 1 - _ease((lt - (dur - 0.18)) / 0.18) if lt > dur - 0.18 else 1.0
        block_h = lh * len(lines)
        y0 = (H - block_h) // 2 - 40
        k = 0
        for li, line in enumerate(lines):
            x = MARGIN
            for w, hl, ww, sp in line:
                x += sp
                wt = (k / max(1, n_words)) * reveal
                p = _ease((lt - wt) / 0.22)
                if p > 0:
                    c = accent if hl else text_col
                    a = int(255 * p * fade_out)
                    d.text((x, y0 + li * lh + int(28 * (1 - p))), w, font=font, fill=c[:3] + (a,))
                x += ww
                k += 1

        # footer: handle + progress bar
        d.text((MARGIN, H - 250), cfg["handle"], font=handle_font, fill=muted)
        d.rounded_rectangle((MARGIN, H - 180, W - MARGIN, H - 170), radius=5, fill=(255, 255, 255, 40))
        d.rounded_rectangle((MARGIN, H - 180, MARGIN + int((W - 2 * MARGIN) * t / total), H - 170),
                            radius=5, fill=accent)

        frame.alpha_composite(layer)
        ff.stdin.write(frame.convert("RGB").tobytes())

    ff.stdin.close()
    code = ff.wait()
    ff_log.seek(0)
    err = ff_log.read()
    ff_log.close()
    if code != 0:
        raise RuntimeError(f"ffmpeg failed:\n{err[-2000:]}")
    return out, total
