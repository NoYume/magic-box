# Hardware

**Owner:** Daniel + Enoch

## Parts

| Part | Notes |
|---|---|
| ZED X | GMSL2 through a ZED Link capture card. Has an IMU, so body tracking is supported. GMSL2 is not hot-pluggable. |
| Jetson Orin Nano | RAM and JetPack version unconfirmed. Checking them is step 1 on the device (`uv run python scripts/check_env.py`). The dev kit's video output is **DisplayPort**, so use a DP-to-HDMI adapter if the monitor needs HDMI. |
| Monitor | External, 1920x1080 assumed. This is the console's main display. |
| Mics | One clip-on lav mic per player (better in a noisy room than one big mic). Either two USB lav mics, or a dual-transmitter wireless kit whose USB receiver puts P1 on the L channel and P2 on R. An external USB mic is a spare. |
| Network | Wi-Fi on the Jetson, for the Muse APIs. |

## Mic routing

Mic devices are per machine, so they go in `config.local.yaml` (gitignored), not `config.yaml`. Each entry maps a player slot to an audio device and channel. Slot 0 is P1 (stands left), slot 1 is P2.

```yaml
# config.local.yaml
voice:
  mics:
    - {slot: 0, device: "USB Lav Mic 1", channel: 0}
    - {slot: 1, device: "USB Lav Mic 2", channel: 0}
```

For a dual-transmitter wireless kit with one USB receiver, use the same device for both and split by channel (`channel: 0` for P1, `channel: 1` for P2). `device: null` means the system default. Find device names with `uv run python scripts/check_env.py` (it lists the audio devices). Spell keys (P1 `1 2 3`, P2 `8 9 0`) work with no mics at all.

### Hollyland wireless receiver (what we use)

The receiver shows up as `Wireless Microphone` (USB, 48 kHz only; the game resamples to 16 kHz). Map it as one device, P1 on the left channel and P2 on the right:

```yaml
# config.local.yaml
voice:
  mics:
    - {slot: 0, device: "Wireless Microphone", channel: 0}
    - {slot: 1, device: "Wireless Microphone", channel: 1}
```

- **Set the receiver to stereo.** It can come up in mono, with both transmitters mixed onto both channels (the two channels are then bit-for-bit identical). On the LARK A1 this is a setting in the LarkSound phone app (plug the receiver into the phone). Check on the Jetson: record both channels while only mic 1 talks; P2's channel should be much quieter.
- **Watch the gain.** The same app has 6 gain levels per transmitter. A transmitter that peaks near 0 dBFS clips; aim for about -6 to -10 dBFS on loud speech, and give both transmitters the same level. The Jetson cannot change it (the receiver exposes no volume control over USB).
- **Restart the game after changing `.env` or `config.local.yaml`.** The voice process reads the key and opens the mics only at startup, and `run_demo.sh` only passes `--env-file .env` if the file exists when it launches: `docker compose restart`.
- **Crosstalk.** Both mics hear both players, so in the lobby (where every sentence is a name or class pick) a loud player can rename the other. Keep the clips close to each player's mouth, turn the gain down, and stand apart. Spells are safer: each mic only matches its own player's incantations. The voice process now drops a lobby (or victory) transcript when the other player's mic was louder during it by `voice.crosstalk_margin_db` (6 dB, a guess), so keep both channels' gain about equal.

## ZED placement and play area

- Mount the ZED X under or above the monitor, centered, pointing at the players. Keep it level; tilt changes depth readings.
- The GMSL2 cable runs to the ZED Link card on the Jetson. Plug it in before powering on, and strain-relieve it so nobody tugs it mid-demo.
- P1 stands on the left from the players' view, P2 on the right. P1 appears on the image's right.
- Tape marks on the floor at the `perception.zones` distances (from the camera, in `config.yaml`):
  - **Danger zone:** closer than 1.6 m (`danger_max_m`).
  - **Neutral zone:** 1.6 m to 2.4 m.
  - **Far zone:** 2.4 m and beyond (`far_min_m`).
- Bodies farther than `camera.max_range_m` (3.5 m) are ignored. Mark the far edge of the play area there.
- Keep the two players about a shoulder-width apart or more so tracking can tell them apart. Mount height, tilt and exact tape distances: TBD at the venue; update this file with what works.

## Jetson setup

1. Check the power mode, then set the highest: `sudo nvpmodel -q` (query), `sudo nvpmodel -m <mode>` (set; mode ids vary by JetPack, see the `-q --verbose` output).
2. Lock clocks to max: `sudo jetson_clocks`.
3. Follow the Jetson quickstart in `README.md`, then run `uv run python scripts/check_env.py` and confirm `pyzed` imports inside the venv.
4. Watch thermals during long runs, especially in an enclosure.

## ZED X troubleshooting

- Camera not detected, or `check_env.py` shows `zed_x_daemon` not active: `sudo systemctl restart zed_x_daemon`. If that fails, reboot with the camera plugged in.
- Check the driver bound both sensors: `sudo dmesg | grep zedx`. Both cameras' entries should say "bound".
- `ZED_Diagnostic` (installed with the ZED SDK) tests the camera and the SDK.
- Never re-plug the GMSL2 cable while the Jetson runs. After any re-plug, restart `zed_x_daemon` or reboot.
- The perception process retries opening the camera every `perception.open_retry_s` and logs `ZED X not detected?` with the restart hint.

## Network

- Wi-Fi on the Jetson reaches `api.meta.ai` for voice transcription and Spark. Test it at the venue early.
- **Backup:** a phone hotspot. If both fail, the game still runs: spell keys work, incantations fall back to config, and the chronicle falls back to a template.

## TODOs

- Enclosure (Hardware track): Daniel.
- Mic model and channel routing: Daniel.
- ZED mount height and exact tape distances: Enoch + Daniel.
- Confirm JetPack, Python, RAM and ZED SDK versions, then pin them.
