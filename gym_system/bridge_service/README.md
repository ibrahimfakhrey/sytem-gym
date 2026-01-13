# Fingerprint Bridge Service

This service runs locally at the gym and syncs attendance data from the AAS fingerprint device to the cloud-based gym system.

## Requirements

- Python 3.8+
- Network access to fingerprint device (192.168.1.224:5005)
- Network access to cloud API

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables (or edit bridge.py):
```bash
export GYM_API_URL="https://your-gym-system.railway.app"
export GYM_API_KEY="your-api-key-here"
export FINGERPRINT_IP="192.168.1.224"
export FINGERPRINT_PORT="5005"
export SYNC_INTERVAL="30"
```

3. Run the service:
```bash
python bridge.py
```

## Running as a Windows Service

You can use NSSM (Non-Sucking Service Manager) to run as a Windows service:

```cmd
nssm install GymBridge "C:\Python3x\python.exe" "C:\path\to\bridge.py"
nssm set GymBridge AppDirectory "C:\path\to\bridge_service"
nssm start GymBridge
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| GYM_API_URL | Cloud API URL | https://your-gym-system.railway.app |
| GYM_API_KEY | API authentication key | your-api-key-here |
| FINGERPRINT_IP | Device IP address | 192.168.1.224 |
| FINGERPRINT_PORT | Device port | 5005 |
| SYNC_INTERVAL | Sync interval in seconds | 30 |

## How It Works

1. Bridge service connects to the local fingerprint device
2. Reads new attendance logs periodically
3. Sends attendance data to cloud API
4. Cloud system matches fingerprint IDs to members
5. Creates attendance records in the database

## Enrollment Workflow

1. Create member in web system (auto-generates fingerprint_id)
2. Bridge service shows pending enrollments
3. Register fingerprint in AAS software using the assigned ID
4. Member can now check in via fingerprint

## Logs

Logs are written to `bridge.log` in the same directory.

## Troubleshooting

### Cannot connect to device
- Check network connectivity
- Verify IP address and port
- Ensure device is powered on

### API connection failed
- Check internet connectivity
- Verify API URL is correct
- Check API key

### Sync not working
- Check bridge.log for errors
- Verify fingerprint device protocol
- Ensure member fingerprint IDs match
