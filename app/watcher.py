import subprocess
import sys
import time

from common import DIR, acquire_mutex, any_app_running, log, pythonw

OVERLAY = DIR / "overlay.py"
CREATE_NO_WINDOW = 0x08000000


def launch_overlay():
    with open(DIR / "overlay-stdio.log", "a", encoding="utf-8") as out:
        return subprocess.Popen(
            [pythonw(), str(OVERLAY)],
            cwd=str(DIR),
            creationflags=CREATE_NO_WINDOW,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
        )


def main():
    mutex = acquire_mutex("Local\\OpenChamberTpsWatcher")
    if not mutex:
        return 0

    log("watcher.log", "watcher started")
    proc = None
    launched_for_run = False
    try:
        while True:
            try:
                running = any_app_running()
                if running:
                    if not launched_for_run:
                        proc = launch_overlay()
                        launched_for_run = True
                        log("watcher.log", f"OpenChamber/OpenCode detected, overlay pid={proc.pid}")
                else:
                    if launched_for_run:
                        if proc is not None and proc.poll() is None:
                            try:
                                proc.terminate()
                            except Exception:
                                pass
                        proc = None
                        launched_for_run = False
                        log("watcher.log", "OpenChamber/OpenCode closed, overlay stopped")
            except Exception as error:
                log("watcher.log", f"loop error: {error!r}")
            time.sleep(1.5)
    except KeyboardInterrupt:
        pass
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
