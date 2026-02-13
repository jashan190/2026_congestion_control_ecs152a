# implement udp sender with stop and wait protocol
# packet size is 1024 bytes total: 4-byte seq_id header + up to 1020 bytes payload
# seq_id is a BYTE OFFSET (not packet number)
# measure over 10 iterations
# output ONLY 3 lines (avg throughput, avg delay, avg metric), 7 decimals, no units

import socket
import time

packet_size = 1024
seq_id_size = 4
message_size = packet_size - seq_id_size

PATH = "docker/file.mp3"

FINACK_BODY = b"==FINACK=="

receiver_address = ("localhost", 5001)

throughputs = []
avg_delays = []
metrics = []

for run in range(1):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        # bind to any port other than 5001
        udp_socket.bind(("0.0.0.0", 5002 + run))
        udp_socket.settimeout(0.10)

        start_time = time.perf_counter()

        seq_id = 0           # byte offset
        bytes_sent = 0       # file bytes only (not headers)
        delays = []          # per data-packet delay (first send -> final ack)

        # --- send file data (stop-and-wait) ---
        with open(PATH, "rb") as f:
            while True:
                payload = f.read(message_size)
                if payload == b"":
                    break  # EOF reached, handle EOF handshake after loop

                seq_bytes = int.to_bytes(seq_id, 4, signed=True, byteorder="big")
                packet = seq_bytes + payload

                first_send_time = None

                while True:
                    if first_send_time is None:
                        first_send_time = time.perf_counter()

                    udp_socket.sendto(packet, receiver_address)

                    try:
                        ack_bytes, _ = udp_socket.recvfrom(packet_size)
                    except socket.timeout:
                        continue  # retransmit

                    ack_id = int.from_bytes(ack_bytes[:4], signed=True, byteorder="big")

                    # receiver ACKs "next expected byte offset"
                    if ack_id >= seq_id + len(payload):
                        ack_time = time.perf_counter()
                        delays.append(ack_time - first_send_time)

                        bytes_sent += len(payload)
                        seq_id += len(payload)
                        break
                    # else ignore and keep waiting/retransmitting

        # --- EOF: send empty payload with correct seq_id, wait for its ACK ---
        eof_seq_bytes = int.to_bytes(seq_id, 4, signed=True, byteorder="big")
        eof_packet = eof_seq_bytes + b""

        while True:
            udp_socket.sendto(eof_packet, receiver_address)
            try:
                ack_bytes, _ = udp_socket.recvfrom(packet_size)
            except socket.timeout:
                continue

            ack_id = int.from_bytes(ack_bytes[:4], signed=True, byteorder="big")
            if ack_id >= seq_id:
                break

        # --- wait for FIN message ---
        while True:
            try:
                fin_pkt, _ = udp_socket.recvfrom(packet_size)
            except socket.timeout:
                continue
            msg = fin_pkt[4:]
            if msg == b"fin":
                break

        # --- send FINACK so receiver exits ---
        finack_packet = int.to_bytes(0, 4, signed=True, byteorder="big") + FINACK_BODY
        udp_socket.sendto(finack_packet, receiver_address)

        end_time = time.perf_counter()

        elapsed = end_time - start_time
        throughput = (bytes_sent / elapsed) if elapsed > 0 else 0.0
        avg_delay = (sum(delays) / len(delays)) if delays else 0.0
        metric = (0.3 * (throughput / 1000.0) + 0.7 * (1.0 / avg_delay)) if avg_delay > 0 else 0.0

        throughputs.append(throughput)
        avg_delays.append(avg_delay)
        metrics.append(metric)

avg_throughput = sum(throughputs) / len(throughputs)
avg_packet_delay = sum(avg_delays) / len(avg_delays)
avg_metric = sum(metrics) / len(metrics)

print(f"{avg_throughput:.7f}")
print(f"{avg_packet_delay:.7f}")
print(f"{avg_metric:.7f}")