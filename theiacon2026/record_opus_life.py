#!/usr/bin/env python3
"""Record 20s of the Claude Opus 5.0 variant of the life game.

Unlike the other recorders (which walk git commits), this records a single
one-shot file: ../playground/vibe-life.py, produced by Claude Opus 5.0.

The Opus run took ~15 minutes of agentic time and the resulting game
eventually crashes at runtime, so we capture the first DURATION seconds of
real play before any crash. record_runner.py runs the game in a background
thread and keeps the frames it managed to grab, so a late crash still yields a
usable clip.

Requirements: git(optional), ffmpeg, python3, pygame.
No X server needed (uses SDL dummy driver via record_runner.py).
"""
import json
import os
import subprocess
import sys

# One-shot source file produced by Claude Opus 5.0.
GAME_FILE = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "playground",
    "vibe-life.py"))
DURATION = 20.0
FPS = 30  # vibe-life.py renders at clock.tick(30)

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
RUNNER = os.path.join(HERE, "record_runner.py")
MANIFEST = os.path.join(HERE, "opus_life_manifest.json")

PROMPT = (
    "Make me a simulation game in pygame. It is a game of life with 3 types "
    "of entities: plants, herbivores and carnivores. A plant grows until "
    "eaten. Herbivores and carnivores start with high health; eating gains "
    "health, every turn loses health, at 0 HP they die. Carnivores gain HP "
    "by eating herbivores; herbivores gain HP by eating plants. Herbivores "
    "run away from carnivores; carnivores run toward herbivores to eat them."
)


def main() -> int:
    os.makedirs(ASSETS, exist_ok=True)

    if not os.path.exists(GAME_FILE):
        print(f"ERROR: game file not found: {GAME_FILE}")
        return 1

    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["REC_FPS"] = str(FPS)

    video_name = "opus-life-01.mp4"
    out_mp4 = os.path.join(ASSETS, video_name)

    print(f"[opus] recording {DURATION:.0f}s -> {video_name}")
    proc = subprocess.run(
        [sys.executable, RUNNER, GAME_FILE, out_mp4, str(DURATION)],
        env=env, text=True, capture_output=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)

    ok = proc.returncode == 0 and os.path.exists(out_mp4) \
        and os.path.getsize(out_mp4) > 0

    manifest = [{
        "order": 1,
        "model": "Claude Opus 5.0",
        "subject": "one-shot spec (Claude Opus 5.0)",
        "prompt": PROMPT,
        "agentic_minutes": 15,
        "crashes": True,
        "video": f"assets/{video_name}" if ok else None,
        "ok": ok,
    }]

    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest written to {MANIFEST}")
    print(json.dumps(manifest, indent=2))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
