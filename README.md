# Smirror - Smart TV Remote & Cast

Control and cast to Samsung & Philips Smart TVs from your phone's browser. No app install needed — runs entirely as a web page via GitHub Pages.

## Quick Start (Phone)

1. **Enable GitHub Pages** on this repo:
   - Go to repo Settings > Pages
   - Set Source to "Deploy from a branch"
   - Set Branch to `main` (or your branch), folder `/docs`
   - Save

2. **Connect to hotel WiFi** on both your phone and make sure the TV is on

3. **Find the TV's IP address:**
   - On the TV: Settings > Network > Network Status
   - Note the IP (e.g., `192.168.1.100`)

4. **Open the web app** on your phone browser:
   ```
   https://<your-username>.github.io/Smirror/
   ```

5. **Select your TV brand** (Samsung or Philips)

6. **For Samsung TVs:** Accept the TV's certificate (one-time):
   - The app will show a link — tap it
   - Tap "Advanced" > "Proceed" on the browser warning
   - Go back to the app

7. **Enter the TV IP** and tap **Connect**
   - Samsung: The TV will show a pairing prompt — select "Allow"
   - Philips: The app connects via HTTP REST API automatically
   - You're connected!

## Features

### Remote Control
- Full D-pad navigation (up/down/left/right/OK)
- Volume & channel controls
- Power, Home, Back, Source buttons
- Playback controls (play/pause/rewind/fast-forward)
- Number pad for channel entry

### Cast & Stream
- **Open any URL** on the TV's browser (YouTube links, photo URLs, streams)
- **Launch YouTube** videos directly in the YouTube app
- **Type text** into the TV's search fields from your phone (Samsung)

### Quick Launch Apps
One-tap launch for Netflix, YouTube, Prime Video, Disney+, Hulu, HBO Max, Plex, Spotify, and the browser. App list automatically switches between Samsung and Philips app IDs.

## How It Works

### Samsung TVs
The web app connects to the Samsung TV's WebSocket API (`wss://TV_IP:8002`) directly from your phone's browser. This is the same protocol used by the Samsung SmartThings app.

### Philips TVs
The web app connects to the Philips TV's JointSpace REST API (`http://TV_IP:1925/6/`) via HTTP. This is the same protocol used by the Philips TV Remote app. Keys and commands are sent as simple HTTP POST requests.

**Common to both:**
- **No server needed** — it's a static HTML page
- **Settings saved** — reconnects automatically next time
- **Haptic feedback** — vibrates on button press (supported phones)

## Hotel WiFi Tips

- Make sure your phone and the TV are on the **same WiFi network**
- Find the TV's IP from: TV Settings > Network > Network Status
- Some hotel networks isolate devices — if you can't connect:
  - Ask the front desk if there's a "casting" or "media" network
  - Try the TV's WiFi Direct feature instead
- The TV must be powered **on** (not just standby on older models)

## Supported TVs

### Samsung Smart TVs (Tizen OS, 2016+)
- K/KU/KS (2016), M/MU (2017), N/NU (2018), R/RU (2019)
- T/TU (2020), AU (2021), BU/B (2022), CU/C (2023), DU/D (2024+)

### Philips Smart TVs (2014+)
- Android TV models (2014+)
- Saphi platform models (2017+)
- Models with JointSpace API enabled

## Also Includes: Python CLI Tool

If you have a laptop on the same network, you can also use the Python CLI:

```bash
pip install -r requirements.txt

# Discover all TVs (Samsung & Philips)
python -m smirror discover

# Mirror your laptop screen to the TV
python -m smirror mirror --ip 192.168.1.100

# Remote control (auto-detects brand)
python -m smirror remote --ip 192.168.1.100 --key KEY_VOLUP

# Force a specific brand
python -m smirror remote --ip 192.168.1.100 --type philips --key VolumeUp

# Pair with a Philips TV (if required)
python -m smirror pair --ip 192.168.1.100
```

## License

MIT
