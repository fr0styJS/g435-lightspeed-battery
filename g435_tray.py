"""Tray icon showing the G435 battery read over the LIGHTSPEED dongle.

    pip install pystray pillow
    pythonw g435_tray.py

Every reading enters the dongle's bootloader mode, which mutes USB audio for
about 0.8 s, so auto-refresh is opt-in (default: off).
"""
import os, sys, time, threading
import winreg

from PIL import Image, ImageDraw, ImageFont

try:
    import pystray
except ImportError:
    print("pystray is missing:  pip install pystray pillow")
    sys.exit(1)

from g435_battery import read_battery, volts_to_percent, find_device

APP_NAME = "G435 Battery"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
POLLS = [("Off", 0), ("15 min", 15 * 60), ("30 min", 30 * 60), ("60 min", 60 * 60)]
FONT_BOLD = r"C:\Windows\Fonts\arialbd.ttf"

state = {"mv": None, "pct": None, "when": None, "err": None,
         "poll": 0, "busy": False, "last": 0.0}
lock = threading.Lock()


def _font(size):
    try:
        return ImageFont.truetype(FONT_BOLD, size)
    except OSError:
        return ImageFont.load_default()


def make_icon(pct):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if pct is None:
        colour, label = (160, 160, 160, 255), "?"
    else:
        label = str(pct)
        colour = ((110, 230, 125, 255) if pct >= 50 else
                  (245, 200, 80, 255) if pct >= 20 else (255, 120, 105, 255))
    # headphone glyph, left
    d.arc((1, 11, 15, 31), 180, 360, fill=colour, width=3)
    d.rounded_rectangle((0, 20, 5, 33), radius=2, fill=colour)
    d.rounded_rectangle((11, 20, 16, 33), radius=2, fill=colour)
    size = 40 if len(label) == 1 else (34 if len(label) == 2 else 26)
    font = _font(size)
    l, t, r, b = d.textbbox((0, 0), label, font=font)
    d.text((45 - (r - l) / 2 - l, 32 - (b - t) / 2 - t), label, font=font, fill=colour)
    return img


def tooltip():
    if state["err"]:
        return f"{APP_NAME}: {state['err']}"
    if state["pct"] is None:
        return f"{APP_NAME}: no reading yet"
    return f"G435: {state['pct']}%  ({state['mv']} mV)   read {state['when']}"


def refresh(icon=None):
    with lock:
        if state["busy"]:
            return
        state["busy"] = True
    try:
        mv = read_battery()
        if mv is None:
            state.update(mv=None, pct=None, err="headset off or not linked")
        else:
            state.update(mv=mv, pct=volts_to_percent(mv), err=None)
    except Exception as e:                      # keep the icon alive on any fault
        state.update(err=str(e), pct=None, mv=None)
    finally:
        state["when"] = time.strftime("%H:%M:%S")
        state["last"] = time.time()
        state["busy"] = False
        if icon is not None:
            icon.icon = make_icon(state["pct"])
            icon.title = tooltip()


def poller(icon):
    while True:
        time.sleep(2)
        interval = state["poll"]
        if interval and not state["busy"] and time.time() - state["last"] >= interval:
            refresh(icon)


def pythonw():
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def start_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_start(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_ALL_ACCESS) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ,
                              f'"{pythonw()}" "{os.path.abspath(__file__)}"')
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


def set_poll(secs):
    def action(icon, item):
        state["poll"] = secs
    return action


def is_poll(secs):
    def checked(item):
        return state["poll"] == secs
    return checked


def main():
    try:
        find_device()
    except RuntimeError as e:
        print(e)
        return 1

    icon = pystray.Icon(APP_NAME, make_icon(None), tooltip(), menu=pystray.Menu(
        pystray.MenuItem(lambda item: tooltip().replace("   ", "  "), None, enabled=False),
        pystray.MenuItem("Refresh now", lambda i, item: threading.Thread(
            target=refresh, args=(i,), daemon=True).start(), default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Auto-refresh", pystray.Menu(*[
            pystray.MenuItem(label, set_poll(secs), checked=is_poll(secs), radio=True)
            for label, secs in POLLS])),
        pystray.MenuItem("Start with Windows",
                         lambda i, item: set_start(not start_enabled()),
                         checked=lambda item: start_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", lambda i, item: i.stop()),
    ))
    threading.Thread(target=poller, args=(icon,), daemon=True).start()
    threading.Thread(target=refresh, args=(icon,), daemon=True).start()
    icon.run()


if __name__ == "__main__":
    sys.exit(main() or 0)
