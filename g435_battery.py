"""Read the Logitech G435 (Realtek 046D:0ACB) battery over its LIGHTSPEED dongle.

No Logitech software required, no native Python dependencies (talks to
hid.dll through ctypes).

Protocol summary (see README.md for the full write-up):

  HID feature report 6 (usage page 0xFFC0, 63 data bytes, 64 with report ID)
    [06, 01, 03, 0...]                 enter bootloader mode
    [06, 08, 03, 0...]                 exit bootloader mode
    [06, 04, 03, 00, len, ...command]  forward a PA command

  PA commands
    LQ  0x0E  E1 01    bridge -> remote mode (forward to the headset)
    OTA 0x06  31       get battery -> "06 80 00 <u16 LE millivolts>"
    LQ  0x0E  E1 00    bridge -> local mode

Reading the headset battery requires bootloader mode, which mutes the USB
audio for roughly 0.8 s. There is no passive/status channel on this dongle.
"""
import sys, time, ctypes, argparse

import hidwin
from ctypes import wintypes as w
from hidwin import hid

VID, PID = 0x046D, 0x0ACB
REPORT, FEAT, USAGE_PAGE = 6, 64, 0xFFC0

hid.HidD_SetFeature.argtypes = [w.HANDLE, ctypes.c_void_p, w.ULONG]
hid.HidD_SetFeature.restype = w.BOOL
hid.HidD_GetFeature.argtypes = [w.HANDLE, ctypes.c_void_p, w.ULONG]
hid.HidD_GetFeature.restype = w.BOOL

# Generic 3.7 V Li-ion discharge curve. Logitech does not publish a table for
# the G435, so this is an estimate (the millivolts are exact).
CURVE = [(4200, 100), (4100, 90), (4000, 80), (3900, 65), (3800, 50),
         (3750, 40), (3700, 30), (3650, 20), (3600, 10), (3500, 5), (3300, 0)]


def volts_to_percent(mv):
    if mv >= CURVE[0][0]:
        return 100
    for (v_hi, p_hi), (v_lo, p_lo) in zip(CURVE, CURVE[1:]):
        if mv >= v_lo:
            return round(p_lo + (p_hi - p_lo) * (mv - v_lo) / (v_hi - v_lo))
    return 0


def setfeat(h, data):
    buf = ctypes.create_string_buffer(bytes(data) + bytes(FEAT - len(data)), FEAT)
    return bool(hid.HidD_SetFeature(h, buf, FEAT))


def getfeat(h):
    buf = ctypes.create_string_buffer(FEAT)
    buf[0] = bytes([REPORT])
    return buf.raw if hid.HidD_GetFeature(h, buf, FEAT) else None


def send(h, cmdbytes):
    return setfeat(h, bytes([REPORT, 4, 3, 0, len(cmdbytes)]) + cmdbytes)


def ota(cmd, params=b"", counter=0):
    return bytes([0x50, 0x41, 0x06, counter, 1 + len(params), 0x00, cmd]) + params


def lq(cmd, params=b"", counter=0):
    return bytes([0x50, 0x41, 0x0E, counter, 1 + len(params), cmd]) + params


def wait_battery(h, timeout=0.8):
    """Poll for the OTA battery reply; return (mV, payload) or (None, None)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = getfeat(h)
        if r:
            i = r.find(b"\x06\x80\x00", 1)   # category, reply flag, status OK
            if i != -1 and len(r) >= i + 5:
                return r[i + 3] | (r[i + 4] << 8), r[i:i + 7]
        time.sleep(0.03)
    return None, None


def find_device():
    devs = [d for d in hidwin.enumerate(VID, PID) if d["usage_page"] == USAGE_PAGE]
    if not devs:
        raise RuntimeError("G435 dongle (046D:0ACB, Realtek) not found")
    return devs[0]


def read_battery_detail(bootloader=True, verbose=False):
    """Return {'mv': int|None, 'payload': bytes|None} for one reading."""
    d = find_device()
    dev = hidwin.Device(d["path"], out_len=d["out_len"], in_len=d["in_len"])
    dev.drain()
    h = dev.handle
    mv = payload = None
    try:
        if bootloader:
            setfeat(h, bytes([REPORT, 1, 3, 0, 0, 0, 0]))
            time.sleep(0.25)
            getfeat(h)
            if verbose:
                print("bootloader: entered", file=sys.stderr)
        send(h, lq(0xE1, b"\x01"))      # remote mode
        time.sleep(0.15)
        send(h, ota(0x31))              # get battery
        mv, payload = wait_battery(h)
        send(h, lq(0xE1, b"\x00"))      # back to local mode
        time.sleep(0.05)
    finally:
        if bootloader:
            setfeat(h, bytes([REPORT, 8, 3, 0, 0, 0, 0]))
            time.sleep(0.1)
        dev.close()
    return {"mv": mv, "payload": payload}


def read_battery(bootloader=True, verbose=False):
    """Return battery millivolts, or None if the headset is off/unlinked.

    bootloader=False is supported for diagnostics only: the dongle ignores PA
    commands in normal firmware and no reply comes back.
    """
    return read_battery_detail(bootloader=bootloader, verbose=verbose)["mv"]


def main():
    ap = argparse.ArgumentParser(description="Read the G435 battery over LIGHTSPEED.")
    ap.add_argument("--noboot", action="store_true", help="diagnostics only; no reply is expected")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--raw", action="store_true", help="print the reply payload")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    detail = read_battery_detail(bootloader=not a.noboot, verbose=a.verbose)
    dt = time.time() - t0
    mv = detail["mv"]
    if mv is None:
        print("no battery reply (headset off or not linked?)")
        return 2
    pct = volts_to_percent(mv)
    if a.raw:
        print(f"payload: {detail['payload'].hex(' ')}")
    if a.json:
        import json
        print(json.dumps({"mv": mv, "percent": pct, "seconds": round(dt, 2),
                          "payload": detail["payload"].hex()}))
    else:
        print(f"{pct}%  ({mv} mV)  [{dt:.2f}s]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
