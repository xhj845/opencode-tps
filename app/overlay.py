import ctypes
import glob
import json
import os
import sqlite3
import sys
import time
import tkinter as tk
import tkinter.font as tkfont

from common import DIR, acquire_mutex, any_app_running, log

DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")
POS_FILE = DIR / "overlay-pos.json"
SETTINGS_FILE = DIR / "overlay-settings.json"
TRANSPARENT = "#010203"

BG = "#0f141b"
BORDER = "#283445"
FG = "#e8eff8"
MUTED = "#8fa2b8"
DIM = "#5f7088"
GREEN = "#4ade80"
AMBER = "#fbbf24"
BLUE = "#60a5fa"
PURPLE = "#a78bfa"
GRAY = "#64748b"

BALL = 68
PANEL_W = 310
MARGIN = 5
PAD = 10
RADIUS = 14
ROW = 52
MAX_ROWS = 4
ACTIVE = {"waiting", "thinking", "streaming", "tool"}
APPS = {"openchamber", "opencode"}


def cut(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


class Overlay:
    def __init__(self):
        self.mutex = acquire_mutex("Local\\OpenChamberTpsOverlay")
        if not self.mutex:
            log("overlay.log", "another overlay owns the mutex; exiting")
            sys.exit(0)

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.rounded = True
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT)
            self.root.configure(bg=TRANSPARENT)
        except Exception:
            self.rounded = False
            self.root.configure(bg=BG)

        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()

        self.f_title = tkfont.Font(family="Microsoft YaHei UI", size=-12)
        self.f_status = tkfont.Font(family="Microsoft YaHei UI", size=-9)
        self.f_speed = tkfont.Font(family="Consolas", size=-24)
        self.f_unit = tkfont.Font(family="Microsoft YaHei UI", size=-8)
        self.f_ball = tkfont.Font(family="Consolas", size=-20)
        self.f_ball_unit = tkfont.Font(family="Microsoft YaHei UI", size=-7)
        self.f_count = tkfont.Font(family="Consolas", size=-7, weight="bold")

        self.canvas = tk.Canvas(self.root, bg=TRANSPARENT if self.rounded else BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        saved = self.load_settings()
        self.mode = saved.get("mode", "ball")
        if self.mode not in ("ball", "panel"):
            self.mode = "ball"
        self.W = BALL if self.mode == "ball" else PANEL_W
        self.H = BALL if self.mode == "ball" else 82
        self.x, self.y = self.load_position()

        self.visible = False
        self.hidden_until = 0.0
        self.last_app_check = 0.0
        self.absent_since = 0.0
        self.last_title_fetch = 0.0
        self.titles = {}
        self.order = []
        self.last_seen = {}
        self.layout_key = None
        self.ball_items = {}
        self.panel_items = {}
        self.rows = []
        self._press = None
        self._drag = None
        self._states = []
        self.last_top = 0.0

        self.build_ball()
        self.build_panel()
        self.set_mode(self.mode, initial=True)
        self.root.after(120, self.tick)
        self.root.mainloop()

    def load_settings(self):
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_settings(self):
        try:
            SETTINGS_FILE.write_text(json.dumps({"mode": self.mode}), encoding="utf-8")
        except Exception:
            pass

    def load_position(self):
        try:
            data = json.loads(POS_FILE.read_text(encoding="utf-8"))
            x, y = int(data["x"]), int(data["y"])
        except Exception:
            x = self.sw - self.W - 32
            y = 80
        return self.clamp(x, y)

    def clamp(self, x, y):
        return max(0, min(x, max(0, self.sw - self.W))), max(0, min(y, max(0, self.sh - self.H)))

    def save_position(self):
        try:
            POS_FILE.write_text(json.dumps({"x": self.x, "y": self.y}), encoding="utf-8")
        except Exception:
            pass

    def build_ball(self):
        s = BALL
        self.ball_items["circle"] = self.canvas.create_oval(3, 3, s - 3, s - 3, fill=BG, outline=GRAY, width=2, tags="ball")
        self.ball_items["speed"] = self.canvas.create_text(s / 2, s / 2 - 6, text="—", fill=FG, font=self.f_ball, tags="ball")
        self.ball_items["unit"] = self.canvas.create_text(s / 2, s / 2 + 12, text="", fill=MUTED, font=self.f_ball_unit, tags="ball")
        self.ball_items["badge"] = self.canvas.create_oval(s - 19, 1, s - 3, 17, fill=GREEN, outline="", state="hidden", tags="ball")
        self.ball_items["badge_text"] = self.canvas.create_text(s - 11, 9, text="", fill=BG, font=self.f_count, state="hidden", tags="ball")
        for item in self.ball_items.values():
            self.canvas.tag_bind(item, "<ButtonPress-1>", self.on_press)
            self.canvas.tag_bind(item, "<B1-Motion>", self.on_drag)
            self.canvas.tag_bind(item, "<ButtonRelease-1>", self.on_release)
            self.canvas.tag_bind(item, "<Button-3>", self.on_menu)

    def build_panel(self):
        left = MARGIN + PAD
        right = PANEL_W - MARGIN - PAD
        self.panel_items["bg"] = self.canvas.create_polygon(0, 0, 0, 0, fill=BG, outline=BORDER, width=1, tags=("panel", "bg"))
        for index in range(MAX_ROWS):
            top = MARGIN + PAD + index * ROW
            sep = self.canvas.create_line(left, top, right, top, fill=BORDER, width=1, state="hidden", tags=("panel", f"row{index}"))
            bar = self.canvas.create_rectangle(left + 1, top + 9, left + 4, top + ROW - 9, fill=GRAY, outline="", state="hidden", tags=("panel", f"row{index}"))
            title = self.canvas.create_text(left + 12, top + 17, text="", fill=FG, font=self.f_title, anchor="w", state="hidden", tags=("panel", f"row{index}"))
            status = self.canvas.create_text(left + 12, top + 37, text="", fill=MUTED, font=self.f_status, anchor="w", state="hidden", tags=("panel", f"row{index}"))
            speed = self.canvas.create_text(right, top + 20, text="", fill=FG, font=self.f_speed, anchor="e", state="hidden", tags=("panel", f"row{index}"))
            unit = self.canvas.create_text(right, top + 41, text="", fill=MUTED, font=self.f_unit, anchor="e", state="hidden", tags=("panel", f"row{index}"))
            self.rows.append({"sep": sep, "bar": bar, "title": title, "status": status, "speed": speed, "unit": unit})

        for widget in (self.root, self.canvas):
            widget.bind("<ButtonPress-1>", self.on_press)
            widget.bind("<B1-Motion>", self.on_drag)
            widget.bind("<ButtonRelease-1>", self.on_release)
            widget.bind("<Button-3>", self.on_menu)

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="展开面板", command=self.expand)
        self.menu.add_command(label="收起为浮球", command=self.collapse_to_ball)
        self.menu.add_separator()
        self.menu.add_command(label="隐藏 30 秒", command=self.on_close)
        self.menu.add_command(label="退出监控", command=self.quit)

    def draw_panel_bg(self):
        r = RADIUS
        x1, y1 = MARGIN, MARGIN
        x2, y2 = self.W - MARGIN, self.H - MARGIN
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        self.canvas.coords(self.panel_items["bg"], *pts)

    def set_mode(self, mode, initial=False):
        self.mode = mode if mode in ("ball", "panel") else "ball"
        self.save_settings()
        if self.mode == "ball":
            self.canvas.itemconfigure("panel", state="hidden")
            self.W = self.H = BALL
            self.root.attributes("-alpha", 0.82)
            self.canvas.itemconfigure("ball", state="normal")
        else:
            self.canvas.itemconfigure("ball", state="hidden")
            self.canvas.itemconfigure("panel", state="normal")
            self.W = PANEL_W
            self.root.attributes("-alpha", 0.88)
            self.H = MARGIN * 2 + PAD * 2 + ROW if initial else self.H
            self.draw_panel_bg()
        self.x, self.y = self.clamp(self.x, self.y)
        self.root.geometry(f"{self.W}x{self.H}+{self.x}+{self.y}")
        self.render(self._states)

    def force_top(self):
        try:
            user32 = ctypes.windll.user32
            pid = os.getpid()
            found = []
            proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def callback(hwnd, _lparam):
                owner = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                if owner.value == pid:
                    cls = ctypes.create_unicode_buffer(128)
                    user32.GetClassNameW(hwnd, cls, 128)
                    if cls.value == "TkTopLevel":
                        found.append(hwnd)
                return True
            user32.EnumWindows(proc(callback), 0)
            for hwnd in found:
                user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0013)
        except Exception:
            pass

    def on_press(self, event):
        self._press = (event.x_root, event.y_root, time.time(), False)
        self._drag = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def on_drag(self, event):
        if not self._press or not self._drag:
            return
        if abs(event.x_root - self._press[0]) > 4 or abs(event.y_root - self._press[1]) > 4:
            self._press = (self._press[0], self._press[1], self._press[2], True)
        self.x, self.y = self.clamp(event.x_root - self._drag[0], event.y_root - self._drag[1])
        self.root.geometry(f"+{self.x}+{self.y}")

    def on_release(self, _event):
        press = self._press
        self._press = None
        self._drag = None
        if not press:
            return
        if press[3]:
            self.save_position()
        elif time.time() - press[2] < 0.5:
            if self.mode == "ball":
                if self._states:
                    self.expand()
            else:
                self.collapse_to_ball()

    def on_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def on_close(self, _event=None):
        self.hidden_until = time.time() + 30
        self.hide()
        return "break"

    def expand(self):
        if self.mode == "panel" or not self._states:
            return
        self.set_mode("panel")
        self.save_position()
        self.show()

    def collapse_to_ball(self):
        if self.mode == "ball":
            return
        self.set_mode("ball")
        self.save_position()
        self.show()

    def quit(self):
        self.save_position()
        try:
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    def show(self):
        if not self.visible:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.lift()
            self.visible = True
        self.force_top()

    def hide(self):
        if self.visible:
            self.root.withdraw()
            self.visible = False

    def read_states(self):
        now = time.time() * 1000
        merged = {}
        for path in glob.glob(str(DIR / "state-*.json")):
            try:
                if now - os.path.getmtime(path) * 1000 > 12000:
                    continue
                payload = json.load(open(path, "r", encoding="utf-8"))
                if payload.get("app") not in APPS:
                    continue
                if now - float(payload.get("updatedAt") or 0) > 12000:
                    continue
                states = payload.get("sessions") or ([payload["state"]] if payload.get("state") else [])
                for state in states:
                    if not state or not state.get("id"):
                        continue
                    status = state.get("status")
                    last = float(state.get("lastEventAt") or 0)
                    final_at = float(state.get("finalAt") or 0)
                    active = status in ACTIVE and (now - last < 60000 or status == "tool")
                    if status == "waiting" and not state.get("modelID") and not state.get("firstTokenAt"):
                        active = now - last < 8000
                    final = status in {"final", "idle"} and final_at and now - final_at < 5000
                    if not active and not final:
                        continue
                    sid = state["id"]
                    old = merged.get(sid)
                    if not old or last > float(old.get("lastEventAt") or 0):
                        merged[sid] = state
            except Exception:
                continue
        return merged

    def stable_states(self, merged):
        now = time.time()
        for sid in merged:
            self.last_seen[sid] = now
            if sid not in self.order:
                self.order.append(sid)
        for sid in list(self.order):
            if sid not in merged and now - float(self.last_seen.get(sid) or 0) > 10:
                self.order.remove(sid)
        return [merged[sid] for sid in self.order if sid in merged]

    def fetch_titles(self, states):
        now = time.time()
        if now - self.last_title_fetch < 1:
            return
        self.last_title_fetch = now
        needed = []
        for state in states:
            sid = state.get("id")
            cached = self.titles.get(sid)
            if sid and (not cached or now - float(cached.get("at") or 0) > 10):
                needed.append(sid)
        if not needed:
            return
        if not os.path.exists(DB_PATH):
            for sid in needed:
                self.titles[sid] = {"title": "", "directory": "", "parent": None, "at": now}
            return
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=0.2)
            marks = ",".join("?" for _ in needed)
            rows = conn.execute(f"select id, title, directory, parent_id from session_v2 where id in ({marks})", needed).fetchall()
            conn.close()
            found = set()
            for sid, title, directory, parent in rows:
                self.titles[sid] = {"title": title or "", "directory": directory or "", "parent": parent, "at": now}
                found.add(sid)
            for sid in needed:
                if sid not in found:
                    self.titles[sid] = {"title": "", "directory": "", "parent": None, "at": now}
        except Exception:
            for sid in needed:
                self.titles[sid] = {"title": "", "directory": "", "parent": None, "at": now + 10}

    def label(self, state):
        sid = str(state.get("id") or "")
        meta = self.titles.get(sid) or {}
        title = meta.get("title") or ""
        if not title:
            directory = meta.get("directory") or state.get("directory") or ""
            if directory:
                title = os.path.basename(str(directory).replace(chr(92), "/").rstrip("/"))
        if not title:
            title = "会话 " + sid[-6:]
        if meta.get("parent"):
            title = "↳ " + title
        return cut(title, 18)

    def speed_of(self, state):
        status = state.get("status") or "waiting"
        if status in {"final", "idle"} and state.get("exact"):
            return float(state.get("avgTps") or 0), "平均", PURPLE
        if status == "tool":
            return None, "工具", BLUE
        tps = float(state.get("tps") or 0)
        if tps < 0.5:
            return None, "等待", AMBER if status == "thinking" else GRAY
        return tps, "≈ tok/s", GREEN if status == "streaming" else AMBER

    def render_ball(self, states):
        active = [s for s in states if s.get("status") in ACTIVE]
        scored = []
        for state in active:
            speed, _u, _c = self.speed_of(state)
            if speed is not None and speed >= 1:
                scored.append((speed, state))
        top = max(scored, key=lambda item: item[0])[1] if scored else (active[0] if active else None)
        if top:
            speed, unit, color = self.speed_of(top)
            if top.get("status") == "tool":
                text, unit_text = "—", "工具"
            elif speed is not None and speed >= 1:
                text, unit_text = f"{speed:.0f}", unit
            else:
                text, unit_text = "—", unit or "待机"
            count = len(active) if len(active) > 1 else 0
        else:
            text, unit_text, color, count = "—", "待机", GRAY, 0
        self.canvas.itemconfigure(self.ball_items["circle"], outline=color)
        self.canvas.itemconfigure(self.ball_items["speed"], text=text)
        self.canvas.itemconfigure(self.ball_items["unit"], text=unit_text)
        if count:
            self.canvas.itemconfigure(self.ball_items["badge"], state="normal", fill=color)
            self.canvas.itemconfigure(self.ball_items["badge_text"], state="normal", text=str(count))
        else:
            self.canvas.itemconfigure(self.ball_items["badge"], state="hidden")
            self.canvas.itemconfigure(self.ball_items["badge_text"], state="hidden")

    def render_panel(self, states):
        visible = states[:MAX_ROWS]
        if not visible:
            return
        left = MARGIN + PAD
        right = PANEL_W - MARGIN - PAD
        for index, row in enumerate(self.rows):
            if index < len(visible):
                state = visible[index]
                status = state.get("status") or "waiting"
                speed, unit, color = self.speed_of(state)
                if speed is not None and speed >= 1:
                    text, unit_text = f"{speed:.0f}", unit
                elif status in {"waiting", "thinking"}:
                    text, unit_text = "…", ""
                else:
                    text, unit_text = "—", ""
                status_text = {
                    "waiting": "等待", "thinking": "思考中", "streaming": "输出中",
                    "tool": "工具中", "final": "完成", "idle": "空闲",
                }.get(status, status)
                if status == "tool":
                    ms = float(state.get("toolElapsedMs") or 0)
                    if ms > 0:
                        status_text = f"工具中 {ms / 1000:.1f}s"
                self.canvas.itemconfigure(row["bar"], fill=color, state="normal")
                self.canvas.itemconfigure(row["title"], text=self.label(state), state="normal")
                self.canvas.itemconfigure(row["status"], text=status_text, fill=color, state="normal")
                self.canvas.itemconfigure(row["speed"], text=text, state="normal")
                self.canvas.itemconfigure(row["unit"], text=unit_text, state="normal")
                self.canvas.itemconfigure(row["sep"], state="normal" if index else "hidden")
            else:
                for key in ("bar", "title", "status", "speed", "unit", "sep"):
                    self.canvas.itemconfigure(row[key], state="hidden")

        rows = max(1, len(visible))
        height = MARGIN * 2 + PAD * 2 + rows * ROW
        key = (self.mode, len(visible))
        if key != self.layout_key or height != self.H:
            self.layout_key = key
            self.H = height
            self.draw_panel_bg()
            self.x, self.y = self.clamp(self.x, self.y)
            self.root.geometry(f"{self.W}x{self.H}+{self.x}+{self.y}")

    def render(self, states):
        if self.mode == "ball":
            self.render_ball(states)
        else:
            self.render_panel(states)

    def tick(self):
        try:
            now = time.time()
            if now - self.last_app_check > 2:
                self.last_app_check = now
                if any_app_running():
                    self.absent_since = 0.0
                else:
                    self.absent_since = self.absent_since or now
                    if now - self.absent_since > 4:
                        self.quit()
            if now - self.last_top > 1.0:
                self.last_top = now
                self.force_top()
            states = self.stable_states(self.read_states())
            self._states = states
            self.fetch_titles(states)
            if now < self.hidden_until:
                self.hide()
                return
            active = [state for state in states if state.get("status") in ACTIVE]
            if not active:
                if self.mode == "panel":
                    self.set_mode("ball")
                self.hide()
                return
            self.render(states)
            self.show()
        except Exception as error:
            log("overlay.log", f"tick failed: {error!r}")
        finally:
            self.root.after(150, self.tick)


def main():
    log("overlay.log", "overlay starting")
    try:
        Overlay()
    except Exception as error:
        log("overlay.log", f"fatal: {error!r}")
        raise


if __name__ == "__main__":
    main()
