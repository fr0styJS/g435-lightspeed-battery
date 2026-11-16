# g435-lightspeed-battery

Battery readout for the **Logitech G435** over its **LIGHTSPEED USB receiver**, with no Logitech software installed.

This targets the **original Realtek receiver, `046D:0ACB`** — the variant that Logitech's own tooling (and every third-party battery app) does not support. The newer Holtek receiver (`046D:0ADF`) uses a completely different bridge protocol; see [Credits](#credits).

```
> python g435_battery.py
55%  (3831 mV)  [0.83s]
```

## Why this is possible at all

The G435 does **not** speak HID++ and has **no passive status channel**. Confirmed on hardware here:

- 0 frames on either vendor HID collection across idle, volume keys, mute, two power cycles and repeated USB-C charge events
- consumer reports (`03 e9` / `03 ea` for volume) arrive fine, so the capture path itself works
- the dongle answers feature-report reads only after something has been queued

What the dongle *does* expose is the Realtek/PA command bridge, and that can be driven from userspace.

## Protocol

### HID interfaces (`046D:0ACB`)

| Collection | Usage page | Reports |
|---|---|---|
| Consumer control | `0x000C` | in 5 |
| Telephony | `0x000B` | in 5 |
| Vendor control | `0xFFC0` | in 8, out 515, **feature 64** |
| Vendor status | `0xFFC3` | in 21 (report `0x34`), out 3 |

Only the `0xFFC0` collection matters. The control channel is **feature report 6**, 63 data bytes (64 with the report ID), written with `HidD_SetFeature`; acks arrive as 7-byte **input** reports (`06 5a` = OK).

### Framing

```
[06, 01, 03, 0 ... ]                  enter bootloader mode
[06, 08, 03, 0 ... ]                  exit bootloader mode
[06, 04, 03, 00, len, ...PA command]  send a PA command
```

### PA commands

Audiowise `'P','A'` frames, big-endian header:

```
OTA  category 0x06:  50 41 06 <counter> <len> 00 <cmd> [params]
LQ   category 0x0E:  50 41 0E <counter> <len> <cmd> [params]
```

Battery read sequence:

1. enter bootloader (`06 01 03`)
2. `LQ 0x0E E1 01` — bridge to **remote mode**, so commands are forwarded to the headset instead of answered by the dongle
3. `OTA 0x06 0x31` — get battery
4. `LQ 0x0E E1 00` — back to local mode
5. exit bootloader (`06 08 03`)

### Replies

Responses come back through `HidD_GetFeature` as `P I` frames:

```
50 49 <type> <seq> <timestamp u32 LE, ms> <length u16 LE> <payload>
```

The battery reply payload is:

```
06 80 00 <millivolts u16 LE> 00 00
```

Measured on this unit: `06 80 00 00 0F 00 00` = `0x0F00` = **3840 mV**, stable to ±10 mV across reads, and consistent with the headset's green LED band.

Two easy traps, both hit during development:

- **Local mode answers too.** Without the `E1 01` switch the dongle replies `06 80 00 66 00 00 00` (`102`) — its own value, not the headset's — and it keeps answering even with the headset powered off.
- **The prefix is not always present.** The first feature read after entering bootloader can come back without the `P I` pair, so parse by searching for `06 80 00` rather than assuming a fixed offset.

## Cost: ~0.8 s of silence per reading

PA commands are only serviced by the bridge's **bootloader** firmware. Entering it mutes USB audio; exiting restores it. This is why the tool offers *on-demand* reads by default and treats auto-refresh as opt-in.

`--noboot` exists for diagnostics only and returns no reply.

## Usage

```bash
git clone https://github.com/fr0styJS/g435-lightspeed-battery
cd g435-lightspeed-battery
```

```bash
python g435_battery.py              # 55%  (3831 mV)  [0.83s]
python g435_battery.py --json       # {"mv": 3837, "percent": 56, "seconds": 0.84}
python g435_battery.py --noboot     # diagnostics: expects "no battery reply"
```

Tray icon (optional):

```bash
pip install pystray pillow
pythonw g435_tray.py
```

Menu: *Refresh now*, *Auto-refresh* (off / 15 / 30 / 60 min), *Start with Windows*, *Quit*.

## Accuracy

The **millivolts are exact**. The percentage is derived from a generic 3.7 V Li-ion discharge curve; Logitech publishes no table for the G435, and the official guidance is only the LED band (green 31–100%, red 15–30%, flashing red <15%). Expect a few points of error, worse mid-discharge.

Because the gauge is voltage-based, it reads **optimistically while charging**: the cell sits at ~4.10–4.20 V on charge, so a unit that reads ~88% at rest shows ~90% while plugged in. Measured on this unit: 3816–3828 mV unplugged, 4080–4104 mV charging.

## Requirements

- Windows 10/11, Python 3.8+
- No native dependencies: `hidwin.py` is a small ctypes layer over `hid.dll`
- `pystray` + `pillow` only for the tray icon

## Caveats

- Tested on one receiver (`046D:0ACB`, serial `202105190004`) and one headset.
- Bootloader entry is a firmware-update mode. This tool only enters it, reads battery state and exits, and never writes flash — but do not add commands you have not identified.
- If a run ever leaves the dongle unresponsive, unplug and replug it; nothing persistent is stored.

## Credits

- [USB HID Down the rabbit hole: Logitech G435 dongle](https://dev.to/endes/usb-hid-down-the-rabbit-hole-logitech-g435-dongle-33if) — the HID descriptor, the RTK/PA split, the bootloader requirement, and the remote-mode pairing sequence.
- [DsGrilo/G435-Battery-app](https://github.com/DsGrilo/G435-Battery-app) — the Holtek-variant PA command layout (`OTA 0x31`, the voltage curve), which carried over.
- Solaar and HaloBattery — the negative results (no HID++, no dongle battery) that ruled out the obvious paths.

Not affiliated with or endorsed by Logitech. Logitech, G435 and LIGHTSPEED are trademarks of Logitech.
