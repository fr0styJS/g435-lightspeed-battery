# AGENTS.md

Guidance for automated or AI contributors. Read `CHANGELOG.md` first: it holds
the protocol findings and the traps that shaped this code.

## What this repo is

A battery reader for the **Logitech G435** over its **Realtek LIGHTSPEED
receiver `046D:0ACB`**. Core is stdlib-only Python (`ctypes` over `hid.dll`).
`pystray` + `pillow` are optional, only for the tray icon.

## Hardware invariants

- **`046D:0ACB` only.** The newer Holtek variant `046D:0ADF` uses a different
  bridge protocol; do not "fix" this repo to handle both without a device to
  test on.
- The dongle has **no HID++** and **no passive status channel**. Any change
  that polls input reports is wasted effort — this was measured, not assumed.
- PA commands only work in **bootloader mode**, and only reach the headset in
  **remote mode** (`LQ 0x0E E1 01`). Without that switch the dongle answers
  locally with `102`, even with the headset off.

## Safety rules

- Always send `exit bootloader` in a `finally`. Leaving the dongle there means
  no audio until it is replugged.
- Only send identified commands. The bridge also exposes DFU entry and USB
  VID/PID rewriting; an unidentified command can brick the receiver until it is
  reflashed.
- Nothing in this repo writes flash. Keep it that way.

## Testing without guessing

```
python g435_battery.py --raw
```

Expected output with the headset linked:

```
payload: 06 80 00 f0 0f 00 00
88%  (4080 mV)  [0.83s]
```

- Charging raises the value by ~250 mV within seconds; use that to confirm a
  reading is live.
- `--noboot` should print `no battery reply` — it is a negative control, not a
  broken flag.
- Powering the headset off must produce `no battery reply`, not a number. If
  you see a number with the headset off, you are reading the local value and
  the remote-mode step is missing or malformed.

## Style

- Core modules: standard library only. The tray may import `pystray`/`pillow`,
  but must fail with a clear message when they are absent.
- Keep audio-muting work minimal; each bootloader session costs ~0.8 s of
  silence, so do not add retries that enter bootloader more than once.
- `CHANGELOG.md` is the canonical place for protocol detail. Update it when a
  finding changes.
