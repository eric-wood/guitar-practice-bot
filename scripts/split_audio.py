# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""Split the weekly Guitar Aerobics tracks into one file per day/exercise.

Each exercise begins with a metronome count-in. We locate the clicks by
cross-correlating the audio against a click sampled from week 1, group nearby
clicks into count-ins, and keep the strongest count-ins (one per exercise).

    uv run scripts/split_audio.py detect   # writes data/audio_splits.json
    uv run scripts/split_audio.py cut      # writes data/audio/days/*.mp3

Weeks in audio_splits.json marked "manual": true are never overwritten by
`detect`, so hand-corrected start times survive re-runs.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent.parent / "data"
AUDIO = DATA / "audio"
OUT = AUDIO / "days"
SPLITS = DATA / "audio_splits.json"

SR = 11025
TEMPLATE_SOURCE = "01 - Week One - Exercises 1-7.mp3"
TEMPLATE_AT = 1.63  # seconds; second click of week 1's first count-in
TEMPLATE_LEN = 0.1
CLICK_THRESHOLD = 0.85  # normalized cross-correlation
CLUSTER_GAP = 1.5  # clicks closer than this belong to the same count-in
BEAT_TOLERANCE = 0.05  # allowed drift in click spacing within a count-in
QUIET_RMS = 10 ** (-55 / 20)  # -55 dBFS
MAX_CLICKS = 6  # longer runs are sparse music, not a count-in
PRE_ROLL = 0.05  # start each cut slightly before the first click


def load(path):
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(pcm, np.int16).astype(np.float64) / 32768


def click_template():
    x = load(AUDIO / TEMPLATE_SOURCE)
    start = int(TEMPLATE_AT * SR)
    tpl = x[start : start + int(TEMPLATE_LEN * SR)]
    tpl = tpl - tpl.mean()
    return tpl / np.linalg.norm(tpl)


def find_clicks(x, tpl):
    n = len(x) + len(tpl)
    size = 1 << (n - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(x, size) * np.conj(np.fft.rfft(tpl, size)), size)
    corr = corr[: len(x) - len(tpl)]
    energy = np.sqrt(np.convolve(x**2, np.ones(len(tpl)), "valid")[: len(corr)]) + 1e-9
    ncc = corr / energy

    clicks = []
    i = 0
    while i < len(ncc):
        if ncc[i] > CLICK_THRESHOLD:
            peak = i + int(np.argmax(ncc[i : i + int(0.1 * SR)]))
            clicks.append(peak / SR)
            i = peak + int(0.2 * SR)
        else:
            i += 1
    return clicks


def quiet_after(x, t):
    """True if the audio just after a click is near-silent, as in a count-in."""
    seg = x[int((t + 0.15) * SR) : int((t + 0.35) * SR)]
    return len(seg) > 0 and np.sqrt((seg**2).mean()) < QUIET_RMS


def count_ins(x, clicks):
    """Runs of evenly spaced clicks with silence between them."""
    groups = []
    for t in clicks:
        g = groups[-1] if groups else None
        if g and quiet_after(x, g[-1]) and t - g[-1] < CLUSTER_GAP:
            beat = g[1] - g[0] if len(g) > 1 else t - g[-1]
            if abs((t - g[-1]) - beat) < BEAT_TOLERANCE * beat:
                g.append(t)
                continue
        groups.append([t])
    return [g for g in groups if 2 <= len(g) <= MAX_CLICKS]


def exercise_range(name):
    lo, hi = re.search(r"(\d+)\s*-\s*(\d+)\.mp3$", name).groups()
    return int(lo), int(hi)


def detect():
    splits = json.loads(SPLITS.read_text()) if SPLITS.exists() else {}
    tpl = click_template()
    for path in sorted(AUDIO.glob("[0-9][0-9] - Week*.mp3")):
        week = path.name[:2]
        if splits.get(week, {}).get("manual"):
            print(f"week {week}: manual, skipped")
            continue
        lo, hi = exercise_range(path.name)
        expected = hi - lo + 1
        x = load(path)
        groups = count_ins(x, find_clicks(x, tpl))
        # Keep the `expected` largest count-ins, then restore time order.
        chosen = sorted(sorted(groups, key=len, reverse=True)[:expected])
        starts = [round(max(0.0, g[0] - PRE_ROLL), 2) for g in chosen]
        starts[0] = 0.0  # nothing precedes the first exercise
        sizes = [len(g) for g in chosen]
        review = len(groups) != expected or min(sizes) < 3
        splits[week] = {
            "file": path.name,
            "first_exercise": lo,
            "starts": starts,
            "clicks": sizes,
            "review": review,
            "manual": False,
        }
        flag = f"  <-- review ({len(groups)} count-ins found, clicks={sizes})" if review else ""
        print(f"week {week}: {len(starts)}/{expected}{flag}")
    SPLITS.write_text(json.dumps(splits, indent=2) + "\n")


def cut():
    splits = json.loads(SPLITS.read_text())
    OUT.mkdir(exist_ok=True)
    for week, info in sorted(splits.items()):
        src = AUDIO / info["file"]
        starts = info["starts"]
        for i, start in enumerate(starts):
            ex = info["first_exercise"] + i
            dest = OUT / f"ex{ex:03d}-week{week}.mp3"
            cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-i", str(src)]
            if i + 1 < len(starts):
                cmd += ["-t", str(round(starts[i + 1] - start, 3))]
            cmd += ["-map", "0:a", "-c", "copy", "-map_metadata", "-1", str(dest)]
            subprocess.run(cmd, check=True)
        print(f"week {week}: {len(starts)} files")


if __name__ == "__main__":
    {"detect": detect, "cut": cut}[sys.argv[1]]()
