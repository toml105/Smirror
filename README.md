# Smirror - Samsung TV Screen Mirror

A Python tool to discover and mirror your screen to Samsung Smart TVs over a local network (e.g., hotel WiFi).

## How It Works

1. **Discovery** - Scans the local network for Samsung TVs using SSDP (Simple Service Discovery Protocol)
2. **Pairing** - Connects to the TV via Samsung's WebSocket API and requests pairing
3. **Mirroring** - Captures your screen and streams frames to the TV

## Requirements

- Python 3.8+
- Samsung Smart TV (Tizen-based, 2016 or newer) on the same WiFi network
- Your computer and the TV must be on the same network subnet

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Discover TVs on the network

```bash
python -m smirror discover
```

### Mirror your screen to a TV

```bash
# Auto-discover and connect to the first TV found
python -m smirror mirror

# Connect to a specific TV by IP
python -m smirror mirror --ip 192.168.1.100

# Adjust frame rate and quality
python -m smirror mirror --ip 192.168.1.100 --fps 30 --quality 80
```

### Send a remote control command

```bash
python -m smirror remote --ip 192.168.1.100 --key KEY_VOLUP
```

## Hotel WiFi Tips

- Many hotel networks isolate devices (AP isolation). If discovery finds nothing, try:
  - Asking the front desk for the TV's IP address
  - Using `--ip` to connect directly
  - Checking if the hotel has a "casting" or "screen share" network
- Some hotels have Samsung TVs with Hospitality Mode which may restrict connections

## Supported Samsung TV Models

- Samsung Smart TVs running Tizen OS (2016+)
- Models: K/KU/KS series (2016), M/MU series (2017), N/NU series (2018), R/RU series (2019), T/TU series (2020), AU series (2021), BU/B series (2022), CU/C series (2023), DU/D series (2024), and newer

## License

MIT
