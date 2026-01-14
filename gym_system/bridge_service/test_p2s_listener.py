#!/usr/bin/env python3
"""
P2S (Push-to-Server) Test Listener

Run this script to test if the fingerprint device can push events to your PC.
This will listen on a port and display any data received from the device.

Usage:
    python test_p2s_listener.py

Make sure to:
1. Set the device to P2S mode in AAS software
2. Configure Server IP to this PC's IP address
3. Configure Server Port to 7005 (or change PORT below)
"""

import socket
import threading
from datetime import datetime

# Configuration
HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 7005       # Default port - change if needed

def get_local_ip():
    """Get the local IP address of this machine"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def handle_client(client_socket, address):
    """Handle incoming connection from device"""
    print(f"\n{'='*50}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] CONNECTION from {address}")
    print(f"{'='*50}")

    try:
        while True:
            data = client_socket.recv(4096)
            if not data:
                break

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] DATA RECEIVED ({len(data)} bytes):")
            print(f"  HEX: {data.hex()}")
            print(f"  RAW: {data}")

            # Try to decode as text
            try:
                text = data.decode('utf-8', errors='replace')
                print(f"  TXT: {text}")
            except:
                pass

            # Try to identify common patterns
            analyze_data(data)

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        client_socket.close()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connection closed from {address}")

def analyze_data(data):
    """Try to analyze the received data"""
    print("\n  [ANALYSIS]:")

    # Check for common fingerprint event patterns
    if len(data) >= 4:
        # Many devices send user ID in first few bytes
        print(f"    First 4 bytes as int: {int.from_bytes(data[:4], 'little')}")

    if len(data) >= 8:
        print(f"    Bytes 4-8 as int: {int.from_bytes(data[4:8], 'little')}")

    # Look for timestamp patterns (common in attendance data)
    if len(data) >= 10:
        print(f"    Possible data fields detected - length: {len(data)}")

def main():
    local_ip = get_local_ip()

    print("=" * 60)
    print("  P2S (Push-to-Server) TEST LISTENER")
    print("=" * 60)
    print(f"\n  Your PC IP Address: {local_ip}")
    print(f"  Listening on Port:  {PORT}")
    print(f"\n  Configure your fingerprint device with:")
    print(f"    Server IP:   {local_ip}")
    print(f"    Server Port: {PORT}")
    print("\n" + "=" * 60)
    print("  Waiting for connections from fingerprint device...")
    print("  (Scan a fingerprint to test)")
    print("=" * 60 + "\n")

    # Create server socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((HOST, PORT))
        server.listen(5)

        while True:
            client_socket, address = server.accept()
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_socket, address)
            )
            client_thread.start()

    except KeyboardInterrupt:
        print("\n\nShutting down...")
    except Exception as e:
        print(f"\n[ERROR] Could not start server: {e}")
        print(f"Make sure port {PORT} is not in use")
    finally:
        server.close()

if __name__ == '__main__':
    main()
