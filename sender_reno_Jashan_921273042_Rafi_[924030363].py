# Requirements for implementing TCP Reno (Extra Credit)
# packet size (1024 bytes): 4-byte seq_id header + up to 1020 bytes payload
# seq_id is a BYTE OFFSET (not packet number)
# measure over 10 iterations
# output ONLY 3 lines (avg throughput, avg delay, avg metric), 7 decimals, no units, separated by a comma 

import socket
import time
import os
import select

# config stuff
RECEIVER_IP = "localhost"
RECEIVER_PORT = 5001
FILE_PATH = "docker/file.mp3" 

PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MSG_SIZE = PACKET_SIZE - SEQ_ID_SIZE

TIMEOUT = 0.5        # seconds
NUM_ITERATIONS = 1

CWND0 = 1.0
SSTHRESH0 = 64.0


def make_pkt(seq, payload: bytes) -> bytes:
    return int.to_bytes(seq, SEQ_ID_SIZE, signed=True, byteorder="big") + payload


def read_ack(buf: bytes):
    ack_seq = int.from_bytes(buf[:SEQ_ID_SIZE], signed=True, byteorder="big")
    msg = buf[SEQ_ID_SIZE:].decode("utf-8", errors="ignore")
    return ack_seq, msg


def run_sender():
    if not os.path.exists(FILE_PATH):
        return 0.0, 0.0, 0.0

    # load file into "packets" keyed by byte offset
    packets = {}
    seq = 0
    with open(FILE_PATH, "rb") as f:
        while True:
            chunk = f.read(MSG_SIZE)
            if not chunk:
                break
            packets[seq] = chunk
            seq += len(chunk)

    total_bytes = seq
    seqs = sorted(packets.keys())  # for walking ACK ranges

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    cwnd = CWND0
    ssthresh = SSTHRESH0

    base = 0
    next_seq = 0

    # metrics
    first_send_time = {}   # seq -> time()
    delays = []            # ack time - first send time

    start = time.time()
    last_progress = time.time()

    dup_acks = 0

    while base < total_bytes:
        # send as much as window allows
        win_end = base + int(cwnd) * MSG_SIZE

        while next_seq < total_bytes and next_seq < win_end:
            sock.sendto(make_pkt(next_seq, packets[next_seq]), (RECEIVER_IP, RECEIVER_PORT))

            if next_seq not in first_send_time:
                first_send_time[next_seq] = time.time()

            next_seq += len(packets[next_seq])

        # try to read an ACK 
        try:
            r, _, _ = select.select([sock], [], [], 0.01)
            if r:
                data, _ = sock.recvfrom(1024)
                ack_seq, _ = read_ack(data)

                if ack_seq > base:
                    old_base = base

                    # mark all newly ACKed packets and record delay
                    now = time.time()
                    for s in seqs:
                        if s < old_base:
                            continue
                        end = s + len(packets[s])
                        if end <= ack_seq:
                            t0 = first_send_time.pop(s, None)
                            if t0 is not None:
                                delays.append(now - t0)
                        else:
                            break

                    base = ack_seq
                    last_progress = now
                    dup_acks = 0

                    # Reno growth (rough)
                    if cwnd < ssthresh:
                        cwnd += 1.0
                    else:
                        cwnd += 1.0 / cwnd

                elif ack_seq == base:
                    dup_acks += 1
                    if dup_acks == 3:
                        # fast retransmit
                        ssthresh = max(cwnd / 2.0, 2.0)
                        cwnd = ssthresh + 3.0

                        if base < total_bytes:
                            sock.sendto(make_pkt(base, packets[base]), (RECEIVER_IP, RECEIVER_PORT))

        except (BlockingIOError, OSError):
            pass

        # timeout = assume lost packet, go back to slow start
        if time.time() - last_progress > TIMEOUT:
            ssthresh = max(cwnd / 2.0, 2.0)
            cwnd = 1.0
            dup_acks = 0

            if base < total_bytes:
                sock.sendto(make_pkt(base, packets[base]), (RECEIVER_IP, RECEIVER_PORT))

            last_progress = time.time()

    got_fin = False
    for _ in range(10):
        sock.sendto(make_pkt(total_bytes, b""), (RECEIVER_IP, RECEIVER_PORT))
        try:
            r, _, _ = select.select([sock], [], [], 0.5)
            if r:
                data, _ = sock.recvfrom(1024)
                _, msg = read_ack(data)
                if msg == "fin":
                    got_fin = True
                    break
        except Exception:
            pass

    # send finack even if we didn’t see fin (keep things moving)
    sock.sendto(make_pkt(total_bytes, b"==FINACK=="), (RECEIVER_IP, RECEIVER_PORT))
    sock.close()

    dur = time.time() - start
    throughput = total_bytes / dur if dur > 0 else 0.0
    avg_delay = (sum(delays) / len(delays)) if delays else 0.0
    metric = (0.3 * (throughput / 1000.0)) + (0.7 / avg_delay) if avg_delay > 0 else 0.0

    return throughput, avg_delay, metric


if __name__ == "__main__":
    tps, ds, ms = [], [], []

    for _ in range(NUM_ITERATIONS):
        tp, d, m = run_sender()
        tps.append(tp)
        ds.append(d)
        ms.append(m)
        time.sleep(1)

    avg_tp = sum(tps) / len(tps)
    avg_d = sum(ds) / len(ds)
    avg_m = sum(ms) / len(ms)

    print(f"{avg_tp:.7f},{avg_d:.7f},{avg_m:.7f}")
