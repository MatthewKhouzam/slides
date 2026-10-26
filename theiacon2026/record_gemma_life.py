#!/usr/bin/env python3
"""Walk every commit touching gemma-life.py in the vibe-life repo and record
20s of the game at each one.

This is the gemma4:12b (128k context) variant. Each commit message IS the
prompt that produced that version. Records straight from the *origin/main* ref
(it was just fetched) so no checkout churn is needed.

For each commit that contains gemma-life.py we:
  1. extract the file contents at that commit into a temp file,
  2. run the game headlessly for DURATION seconds via record_runner.py,
  3. encode an mp4 into assets/,
and finally write a JSON manifest mapping commit -> subject -> video.

gemma-life.py runs its loop at ~10 FPS (clock.tick(10)); we encode at 10 so
playback is real-time (20s of game == 20s of video).

Requirements: git, ffmpeg, python3, pygame.
No X server needed (uses SDL dummy driver via record_runner.py).
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "vibe-life"))
GAME_FILE = "gemma-life.py"
REF = "origin/main"
DURATION = 20.0
FPS = 10  # gemma-life.py uses clock.tick(10)

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
RUNNER = os.path.join(HERE, "record_runner.py")
MANIFEST = os.path.join(HERE, "gemma_life_manifest.json")


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True,
                          capture_output=True, **kw)


def main() -> int:
    os.makedirs(ASSETS, exist_ok=True)

    log = run(["git", "-C", REPO, "log", "--reverse", "--format=%H",
               REF, "--", GAME_FILE])
    commits = [c for c in log.stdout.splitlines() if c.strip()]
    print(f"Found {len(commits)} commits touching {GAME_FILE}.")

    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["REC_FPS"] = str(FPS)

    manifest = []
    order = 0
    with tempfile.TemporaryDirectory(prefix="gemma-life-") as tmp:
        for commit in commits:
            short = commit[:7]
            subject = run(["git", "-C", REPO, "log", "-1", "--format=%s",
                           commit]).stdout.strip()

            blob = run(["git", "-C", REPO, "show",
                        f"{commit}:{GAME_FILE}"]).stdout
            game_path = os.path.join(tmp, f"gemma-life-{short}.py")
            with open(game_path, "w") as f:
                f.write(blob)

            order += 1
            video_name = f"gemma-life-{order:02d}-{short}.mp4"
            out_mp4 = os.path.join(ASSETS, video_name)

            print(f"[{short}] recording {DURATION:.0f}s -> {video_name} "
                  f"({subject[:60]})")
            proc = subprocess.run(
                [sys.executable, RUNNER, game_path, out_mp4, str(DURATION)],
                env=env, text=True, capture_output=True,
            )
            sys.stdout.write(proc.stdout)
            sys.stderr.write(proc.stderr)

            ok = proc.returncode == 0 and os.path.exists(out_mp4) \
                and os.path.getsize(out_mp4) > 0
            manifest.append({
                "order": order,
                "commit": commit,
                "short": short,
                "subject": subject,
                "video": f"assets/{video_name}" if ok else None,
                "ok": ok,
            })
            if not ok:
                print(f"[{short}] FAILED to record.")

    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest written to {MANIFEST}")
    print(json.dumps(manifest, indent=2))

    return 0 if all(m["ok"] for m in manifest) else 1


if __name__ == "__main__":
    sys.exit(main())
