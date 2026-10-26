#!/usr/bin/env python3
"""Clone the vibe-life repo, walk every commit, and record 20s of the game.

For each commit that contains the pygame game file, we:
  1. checkout the commit,
  2. run the game headlessly for DURATION seconds while capturing frames,
  3. encode an mp4 into assets/,
and finally write a JSON manifest mapping commit -> prompt -> video.

The prompt for each commit is extracted from its commit message.

Requirements: git, ffmpeg, python3, pygame (pip install --user pygame).
No X server needed (uses SDL dummy driver via record_runner.py).
"""
import json
import os
import re
import subprocess
import sys
import tempfile

REPO_URL = "https://github.com/matthewkhouzam/vibe-life.git"
GAME_FILE = "life_game.py"
DURATION = 20.0
FPS = 30

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
RUNNER = os.path.join(HERE, "record_runner.py")
MANIFEST = os.path.join(HERE, "vibe_life_manifest.json")


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True,
                          capture_output=True, **kw)


def extract_prompt(message: str) -> str:
    """Pull the human prompt out of a commit message.

    Handles both `prompt: "..."` one-liners and a `Prompt:` block, and falls
    back to the commit subject line.
    """
    # Strip the sign-off trailer.
    lines = [l for l in message.splitlines()
             if not l.lower().startswith("signed-off-by")]
    text = "\n".join(lines).strip()

    # Pattern A: prompt: "..."
    m = re.search(r'prompt:\s*"(.+?)"', text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()

    # Pattern B: a "Prompt:" block (everything after it).
    m = re.search(r'Prompt:\s*(.+)', text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()

    # Fallback: subject line.
    return text.splitlines()[0].strip() if text else ""


def main() -> int:
    os.makedirs(ASSETS, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="vibe-life-") as tmp:
        repo = os.path.join(tmp, "repo")
        print(f"Cloning {REPO_URL} ...")
        run(["git", "clone", "--quiet", REPO_URL, repo])

        # Oldest -> newest.
        log = run(["git", "-C", repo, "log", "--format=%H", "--reverse"])
        commits = [c for c in log.stdout.splitlines() if c.strip()]
        print(f"Found {len(commits)} commits.")

        env = dict(os.environ)
        env["SDL_VIDEODRIVER"] = "dummy"
        env["SDL_AUDIODRIVER"] = "dummy"
        env["REC_FPS"] = str(FPS)

        manifest = []
        order = 0
        for commit in commits:
            short = commit[:7]
            # Does this commit have the game file?
            tree = run(["git", "-C", repo, "ls-tree", "--name-only",
                        commit])
            if GAME_FILE not in tree.stdout.split():
                print(f"[{short}] no {GAME_FILE}, skipping.")
                continue

            msg = run(["git", "-C", repo, "log", "-1", "--format=%B",
                       commit]).stdout
            subject = run(["git", "-C", repo, "log", "-1", "--format=%s",
                           commit]).stdout.strip()
            prompt = extract_prompt(msg)

            run(["git", "-C", repo, "checkout", "--quiet", commit])

            order += 1
            video_name = f"vibe-life-{order:02d}-{short}.mp4"
            out_mp4 = os.path.join(ASSETS, video_name)
            game_path = os.path.join(repo, GAME_FILE)

            print(f"[{short}] recording {DURATION:.0f}s -> {video_name}")
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
                "prompt": prompt,
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
