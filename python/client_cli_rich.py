import argparse
import traceback
import sys
import os

from client.cli_rich import QUARPConsoleRich

# Configurazione del client
SERVER_IP = "localhost"
SERVER_PORT = 65432

def parse_args():
    parser = argparse.ArgumentParser(
        description="Client per SEA modem (Rich Interface)"
    )
    parser.add_argument(
        "-s", "--server-ip",
        default=SERVER_IP,
        help=f"Indirizzo IP del server (default: {SERVER_IP})"
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=SERVER_PORT,
        help=f"Porta TCP (default: {SERVER_PORT})"
    )
    return parser.parse_args()

if __name__ == "__main__":
    try:
        args = parse_args()
        # Initialize the Rich Console instead of the standard one
        console = QUARPConsoleRich(args.server_ip, args.port)
        console.run()
            
    except Exception as e:
        print(f"Error during execution: {e}")
        print(traceback.format_exc())
