import traceback
import logging
import numpy as np
from datetime import datetime
import json
import argparse

from client.core import QUARPCore
from client.interface import *
from client.utils import ASCII_ART

from client.cli import QUARPConsole

# Import trilateration module (assumed to be in sibling folder)
import trilateration.ls_tdoa_t0 as tr


# === CONFIGURAZIONE ===
SERVER_IP = "192.168.1.49"
SERVER_PORT = 65432

SPEED_SOUND = 1498 # m/s 20 C
T0 = 0.100 
offset = [0, 0, 0, 0]

# === LOGGER ===
logging.basicConfig(
    filename='trilateration.log',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class CroceClient(QUARPCore):
    """
    Client specializzato per l'analisi 'Croce'.
    Gestisce il calcolo della posizione (TDOA/AoA) basato sui pacchetti received.
    """
    def __init__(self, server_ip, server_port):
        super().__init__(server_ip, server_port)
        self.estimated_positions = []
        self.est_plot = None # Placeholder se si vuole attivare il plot
        
        # Assign custom callbacks
        self.on_connected = self.custom_on_connected
        self.on_disconnected = self.custom_on_disconnected
        self.on_error = self.custom_on_error
        
        # Registra i handler specifici sovrascrivendo quelli vuoti del Core
        self.register_handler(FE_TRACKING_CMD, self.handle_tracking)
        self.register_handler(FE_ONE_WAY_RANGE_CMD, self.handle_one_way_range)

    def custom_on_connected(self, ip, port):
        # print(ASCII_ART) # Handled by Console run()
        # print(f"📡 Connected to {ip}:{port}\n") # Handled by Console
        pass

    def custom_on_disconnected(self):
        print("❌ Disconnected from server.")

    def custom_on_error(self, msg):
        print(f"❌ Error: {msg}")
        logging.error(msg)
        
    def handle_tracking(self, packet: ExternalPacket):
        """
        Gestisce i pacchetti di tracking per calcolare TDOA e AoA.
        """
        shifts = packet.tracking_shifts
        factors = packet.tracking_factors

        print(f"\nShifts: {shifts}")
        print(f"Correlation factors: {factors}")
        logging.info(f"Shifts: {shifts} | Correlation: {factors}")

        try:
            # Calcoli di trilaterazione e angolo di arrivo
            tdoa = tr.correlation_to_time(shifts)
            pos_ls, t0 = tr.localize_source(tdoa)
            estimated_theta = tr.estimate_aoa_delta_t(shifts)
            estimated_theta2 = tr.estimate_aoa(shifts)
            
            # Compensazione Tilt
            # yaw=0 se vogliamo risultato relativo alla prua
            theta_comp = tr.estimate_aoa_compensated(
                shifts, 0, packet.pitch, packet.roll - 180
            )
            
            print(f"🧭 Estimated position: x = {pos_ls[0]:.3f} m, y = {pos_ls[1]:.3f} m")
            print(f"\tAngle of arrival: theta = {estimated_theta:.3f}")
            print(f"\tAngle of arrival: theta2 = {estimated_theta2:.3f}")
            print(f"\tAngle of arrival (Compensated): {theta_comp:.3f}")
            
            # Nota: packet.yaw, packet.pitch ... potrebbero essere None se non presenti nel pacchetto
            # Gestiamo il caso gracefully
            if packet.yaw is not None:
                print(f"\tYaw = {packet.yaw:.3f}, Pitch = {packet.pitch:.3f}, Roll = {(packet.roll-180):.3f}")

            self.estimated_positions.append(pos_ls)

            # Log data to JSON
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "pos_ls": pos_ls.tolist() if isinstance(pos_ls, np.ndarray) else pos_ls,
                "estimated_theta": estimated_theta,
                "estimated_theta2": estimated_theta2,
                "theta_comp": theta_comp,
                "yaw": packet.yaw,
                "pitch": packet.pitch,
                "roll": packet.roll,
                "shifts": shifts if isinstance(shifts, list) else shifts.tolist() if isinstance(shifts, np.ndarray) else shifts,
                "factors": factors if isinstance(factors, list) else factors.tolist() if isinstance(factors, np.ndarray) else factors
            }
            
            try:
                with open("tracking_data.jsonl", "a") as f:
                    json.dump(log_entry, f)
                    f.write("\n")
            except Exception as e:
                print(f"⚠️ Errore nel salvataggio su file JSON: {e}")
                logging.warning(f"JSON logging failed: {e}")
    
            # Esempio: aggiornamento plot se implementato
            # if self.est_plot:
            #     tr.update_plot(self.est_plot, self.estimated_positions)

        except Exception as e:
            print(f"⚠️ Errore nel calcolo della posizione: {e}")
            logging.warning(f"Position estimation failed: {e}")
            # traceback.print_exc() # Uncomment for deep debug

    def handle_one_way_range(self, packet: ExternalPacket):
        """
        Gestisce i pacchetti di ranging one-way.
        """
        try:
            # Verifica che i campi necessari esistano
            if packet.range_id is None or packet.time_stamp is None:
                print("Invalid One Way Range packet")
                return

            rid = int(packet.range_id)
            if 0 <= rid < len(offset):
                time_of_arrival = packet.time_stamp - offset[rid]
                
                time_of_transmission = int(time_of_arrival) + T0 * rid 
                distance = SPEED_SOUND * (time_of_arrival - time_of_transmission)

                msg = (f"distance from buoy {rid}: {distance:.2f} m. "
                       f"time of transmission: {time_of_transmission:.6f}, "
                       f"time of arrival: {time_of_arrival:.6f}")
                
                print(msg)
                logging.info(msg)
                
                # --- INIZIO NUOVO CODICE PER LOG JSONL ---
                range_log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "buoy_id": rid,
                    "distance_m": distance,
                    "time_of_transmission": time_of_transmission,
                    "time_of_arrival": time_of_arrival
                }

                try:
                    # Uso l'estensione .jsonl perché stiamo scrivendo una riga alla volta
                    with open("ranging_data.jsonl", "a") as f:
                        json.dump(range_log_entry, f)
                        f.write("\n")
                except Exception as e:
                    print(f"⚠️ Errore nel salvataggio del range su file JSONL: {e}")
                    logging.warning(f"Ranging JSON logging failed: {e}")
                # --- FINE NUOVO CODICE ---

            else:
                 print(f"Range ID {rid} out of logical bounds.")

        except Exception as e:
             logging.error(f"Error handling range packet: {e}")

def parse_args():
    parser = argparse.ArgumentParser(description="QUARP Croce Client")
    parser.add_argument("-s", "--server-ip", default=SERVER_IP, help=f"Server IP (default: {SERVER_IP})")
    parser.add_argument("-p", "--port", type=int, default=SERVER_PORT, help=f"TCP Port (default: {SERVER_PORT})")
    return parser.parse_args()

if __name__ == "__main__":
    try:
        args = parse_args()
        
        # Instantiate our CUSTOM core logic (Trilateration/Tracking)
        custom_core = CroceClient(args.server_ip, args.port)
        
        # Instantiate the Console View, injecting our custom core
        # The Console will handle user input and standard output,
        # while 'custom_core' handles the background logic and specific tracking packets.
        console = QUARPConsole(core_instance=custom_core)
        
        # Run the interactive console
        console.run()
            
    except Exception as e:
        print(f"Error during execution: {e}")
        traceback.print_exc()
