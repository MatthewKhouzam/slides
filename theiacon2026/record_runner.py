#!/usr/bin/env python3
"""Headless recorder for a single pygame "life game" commit.

This module is executed as a subprocess with the checked-out repo on the path.
It monkeypatches pygame's display flip/update so that every frame the game
renders is copied and piped as raw RGB into an ffmpeg process, which encodes an
mp4. The game's own main loop runs in a background thread; after DURATION
seconds we post a QUIT event so the game exits cleanly.

Fully headless: uses the SDL "dummy" video driver, so no X server / Xvfb is
needed. The dummy driver still maintains an off-screen display surface that we
can read via pygame.display.get_surface().

Usage:
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
        python3 record_runner.py <game_file> <output_mp4> <duration_sec>
"""
import os
import sys
import time
import threading
import subprocess

# Force headless drivers before pygame is imported by the game.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402


def main() -> int:
    game_file = sys.argv[1]
    out_mp4 = sys.argv[2]
    duration = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
    fps = int(os.environ.get("REC_FPS", "30"))

    # State shared with the patched flip/update hooks.
    state = {
        "size": None,       # (w, h) once set_mode is called
        "ffmpeg": None,     # ffmpeg subprocess once size is known
        "frames": 0,
        "lock": threading.Lock(),
    }

    real_set_mode = pygame.display.set_mode

    def patched_set_mode(size=(0, 0), *args, **kwargs):
        surf = real_set_mode(size, *args, **kwargs)
        w, h = surf.get_size()
        # ffmpeg wants even dimensions for yuv420p.
        ew, eh = w + (w & 1), h + (h & 1)
        with state["lock"]:
            state["size"] = (w, h, ew, eh)
            if state["ffmpeg"] is None:
                state["ffmpeg"] = subprocess.Popen(
                    [
                        "ffmpeg", "-y", "-loglevel", "error",
                        "-f", "rawvideo", "-pixel_format", "rgb24",
                        "-video_size", f"{ew}x{eh}",
                        "-framerate", str(fps),
                        "-i", "-",
                        "-pix_fmt", "yuv420p",
                        "-c:v", "libx264", "-preset", "veryfast",
                        "-movflags", "+faststart",
                        out_mp4,
                    ],
                    stdin=subprocess.PIPE,
                )
        return surf

    pygame.display.set_mode = patched_set_mode

    def grab_frame():
        surf = pygame.display.get_surface()
        if surf is None:
            return
        with state["lock"]:
            sz = state["size"]
            proc = state["ffmpeg"]
        if sz is None or proc is None or proc.stdin is None:
            return
        w, h, ew, eh = sz
        if (w, h) != (ew, eh):
            # Pad to even dimensions.
            padded = pygame.Surface((ew, eh))
            padded.blit(surf, (0, 0))
            data = pygame.image.tostring(padded, "RGB")
        else:
            data = pygame.image.tostring(surf, "RGB")
        try:
            proc.stdin.write(data)
            state["frames"] += 1
        except (BrokenPipeError, ValueError):
            pass

    real_flip = pygame.display.flip
    real_update = pygame.display.update

    def patched_flip(*a, **k):
        real_flip(*a, **k)
        grab_frame()

    def patched_update(*a, **k):
        real_update(*a, **k)
        grab_frame()

    pygame.display.flip = patched_flip
    pygame.display.update = patched_update

    # Load and run the game's main() in a background thread.
    import runpy

    game_exc = {}

    def run_game():
        try:
            runpy.run_path(game_file, run_name="__main__")
        except SystemExit:
            pass
        except BaseException as e:  # noqa: BLE001
            game_exc["e"] = e

    t = threading.Thread(target=run_game, daemon=True)
    t.start()

    # Let the game run for `duration` seconds, then ask it to quit.
    deadline = time.time() + duration
    while time.time() < deadline and t.is_alive():
        time.sleep(0.1)

    # Politely request shutdown, then give it a moment.
    try:
        pygame.event.post(pygame.event.Event(pygame.QUIT))
    except Exception:
        pass
    t.join(timeout=3.0)

    # Close ffmpeg cleanly.
    proc = state["ffmpeg"]
    if proc is not None and proc.stdin is not None:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.wait(timeout=30)

    if game_exc:
        sys.stderr.write(f"game error: {game_exc['e']!r}\n")

    if state["frames"] == 0:
        sys.stderr.write("no frames captured\n")
        return 2
    sys.stderr.write(f"captured {state['frames']} frames -> {out_mp4}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
