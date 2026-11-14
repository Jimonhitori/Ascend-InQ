# Ascend InQ

English | [日本語](README.md)

**Ascend in queue** — a League of Legends review tool that helps you climb every time you queue up.

It records your games automatically and lets you review them afterwards with **video + timeline + advice for each key moment**.

- Automatic, very light recording (GPU encoding — about 0.2% total CPU)
- After each game, reads the match from your LoL client and analyzes deaths, objectives, lane differences and more (**no API key needed**)
- Click a key moment on the timeline → jump to that scene and see what you could have done instead
- No recording? The viewer still replays all 10 players on the minimap from position data

> During a game the app only records and checks every few seconds (a tiny request inside your own PC) whether the game is still running. All analysis happens after the game.

## Download & use
1. Download `AscendInQ-windows.zip` from [Releases](https://github.com/Jimonhitori/Ascend-InQ/releases) and unzip it anywhere
2. Run `AscendInQ.exe` → a gold double-arrow icon appears in the system tray (bottom right)
   - On first run it asks to download ffmpeg (free video tool, ~85 MB), which is needed for recording
   - On first run the settings window opens; check the recording folder and press Save
3. Just play LoL. Recording starts when a game starts (red dot on the icon); afterwards the game is analyzed and the viewer opens
4. When you're done, right-click the tray icon → Quit

Everything (recordings, data, reports) is stored next to `AscendInQ.exe`, so you can move or delete the whole folder.

### "Windows protected your PC"
The app is not code-signed, so Windows SmartScreen may warn you on first launch. Click "More info" → "Run anyway". You can also build it yourself from source (below).

## Notes
- **Set LoL's Window Mode to "Borderless".** Fullscreen can produce black recordings (the app detects and tells you).
- **The whole screen is recorded**, including other windows you Alt+Tab to (Discord etc.). Be careful when sharing recordings.
- Turn off auto-recording in other tools (Outplayed, OBS) to avoid double recording.
- Recording is skipped if less than 3 GB is free. A game is about 1 GB; old recordings are deleted beyond the number you keep.
- If the app crashes, recording stops too, and the partial recording is recovered on the next start.

## Settings
Open from the tray menu → Settings…
| Section | Options |
|---|---|
| Game data | From the LoL client (no key, default) / Riot API key (advanced) |
| Recording | Full match / don't record, folder, recordings to keep, quality, frame rate, monitor, mouse cursor |
| After the game | Analyze automatically, open the viewer automatically |
| General | Language (日本語 / English), start with Windows, notifications |

## What it can and can't tell you
- **Can (macro):** where/how you died and where the enemy jungler was, objective participation, CS/gold/XP differences, item timings, roams
- **Can't (micro):** skillshots, trades, exact wave states → check those in the video
- Positions are estimated from one-minute snapshots plus events
- LoL client data has no ward-placement, item-purchase or turret-plate records. Item timings are captured every 15 s while recording (unrecorded games show the final build only). Ward-based advice needs a Riot API key
- Roles come from the replay file when available, otherwise they're inferred from early positions
- **The advice text and the viewer are currently Japanese only** (the app UI and notifications support English)

## Requirements
- Windows 10/11
- For recording: an NVIDIA / AMD / Intel GPU with a hardware encoder
- ffmpeg (downloaded automatically on first run)
- Optional: a Riot API key, to fetch older games or other accounts

## Run from source / build
```
git clone https://github.com/Jimonhitori/Ascend-InQ.git
cd Ascend-InQ
pip install -r requirements.txt
pythonw app.py          # run the tray app
build.bat               # builds dist\AscendInQ\AscendInQ.exe
```
Python 3.10+. Tests: `pip install -r requirements-dev.txt` then `python -m pytest`.

## Disclaimer
Ascend InQ isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

ffmpeg is the LGPL build from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), downloaded only after the user agrees (it is not part of this repository).

## License
MIT ([LICENSE](LICENSE))
