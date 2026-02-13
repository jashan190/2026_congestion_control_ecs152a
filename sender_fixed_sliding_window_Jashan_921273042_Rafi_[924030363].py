# Requirements for implementing Fixed sliding window protocol with size 100 packets (20 points)
# packet size (1024 bytes): 4-byte seq_id header + up to 1020 bytes payload
# seq_id is a BYTE OFFSET (not packet number)
# measure over 10 iterations
# output ONLY 3 lines (avg throughput, avg delay, avg metric), 7 decimals, no units, separated by a comma 

import socket
import time
import os
import select

FILE_PATH = "docker/file.mp3"
RECEIVER_IP = "localhost"
RECEIVER_PORT = 5001

PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
PAYLOAD_SIZE = PACKET_SIZE - SEQ_ID_SIZE

WINDOW_SIZE = 100
TIMEOUT = 0.5
NUM_ITERATIONS = 10


def make_packet(seq_id: int, payload: bytes) -> bytes:
    return int.to_bytes(seq_id, SEQ_ID_SIZE, signed=True, byteorder="big") + payload


def parse_ack(buf: bytes):
    ack_seq = int.from_bytes(buf[:SEQ_ID_SIZE], signed=True, byteorder="big")
    msg = buf[SEQ_ID_SIZE:].decode("utf-8", errors="ignore")
    return ack_seq, msg


def load_packets(path: str):
    if not os.path.exists(path):
        return {}, 0

    packets = {}
    seq = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(PAYLOAD_SIZE)
            if not chunk:
                break
            packets[seq] = chunk
            seq += len(chunk)

    return packets, seq


def run_sender_fixed():
    packets, total_bytes = load_packets(FILE_PATH)
    if total_bytes == 0:
        return 0.0, 0.0, 0.0

    seq_list = sorted(packets.keys())

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.setblocking(False)

    start = time.time()

    base = 0
    next_seq = 0

    first_send = {}   # seq goes to time for first message 
    delays = []
    last_progress = time.time()

    while base < total_bytes:
        win_end = base + WINDOW_SIZE * PAYLOAD_SIZE

        while next_seq < total_bytes and next_seq < win_end:
            sock.sendto(make_packet(next_seq, packets[next_seq]), (RECEIVER_IP, RECEIVER_PORT))

            if next_seq not in first_send:
                first_send[next_seq] = time.time()

            next_seq += len(packets[next_seq])

        try:
            r, _, _ = select.select([sock], [], [], 0.01)
            if r:
                data, _ = sock.recvfrom(PACKET_SIZE)
                ack_seq, _ = parse_ack(data)

                if ack_seq > base:
                    old_base = base
                    now = time.time()

                    for s in seq_list:
                        if s < old_base:
                            continue
                        end = s + len(packets[s])
                        if end <= ack_seq:
                            t0 = first_send.pop(s, None)
                            if t0 is not None:
                                delays.append(now - t0)
                        else:
                            break

                    base = ack_seq
                    last_progress = now

        except (BlockingIOError, OSError):
            pass

        # timeout  
        if time.time() - last_progress > TIMEOUT:
            if base < total_bytes:
                sock.sendto(make_packet(base, packets[base]), (RECEIVER_IP, RECEIVER_PORT))
            last_progress = time.time()

    ack_done = time.time()

    # fin
    for _ in range(10):
        sock.sendto(make_packet(total_bytes, b""), (RECEIVER_IP, RECEIVER_PORT))
        try:
            r, _, _ = select.select([sock], [], [], 0.5)
            if r:
                data, _ = sock.recvfrom(PACKET_SIZE)
                _, msg = parse_ack(data)
                if msg == "fin":
                    break
        except Exception:
            pass

    sock.sendto(make_packet(total_bytes, b"==FINACK=="), (RECEIVER_IP, RECEIVER_PORT))
    sock.close()

    dur = ack_done - start
    tp = (total_bytes / dur) if dur > 0 else 0.0
    avg_delay = (sum(delays) / len(delays)) if delays else 0.0
    metric = (0.3 * (tp / 1000.0)) + (0.7 / avg_delay) if avg_delay > 0 else 0.0

    return tp, avg_delay, metric


if __name__ == "__main__":
    tps, ds, ms = [], [], []

    for _ in range(NUM_ITERATIONS):
        tp, d, m = run_sender_fixed()
        tps.append(tp)
        ds.append(d)
        ms.append(m)
        time.sleep(1)

    avg_tp = sum(tps) / len(tps)
    avg_d = sum(ds) / len(ds)
    avg_m = sum(ms) / len(ms)

    print(f"{avg_tp:.7f},")
    print(f"{avg_d:.7f},")
    print(f"{avg_m:.7f}")