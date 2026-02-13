# Requirements for implementing Fixed sliding window protocol with size 100 packets (20 points)
# packet size (1024 bytes): 4-byte seq_id header + up to 1020 bytes payload
# seq_id is a BYTE OFFSET (not packet number)
# measure over 10 iterations
# output ONLY 3 lines (avg throughput, avg delay, avg metric), 7 decimals, no units, separated by a comma 

import socket
import time
import os
import select

FILE_PATH = 'docker/file.mp3'
RECEIVER_IP = 'localhost'
RECEIVER_PORT = 5001
PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MESSAGE_SIZE = PACKET_SIZE - SEQ_ID_SIZE
WINDOW_SIZE = 100
# retransmit if no ACK received for base within 0.5 seconds
TIMEOUT = 0.5  


def create_packet(seq_id, data: bytes) -> bytes:
    return int.to_bytes(seq_id, SEQ_ID_SIZE, signed=True, byteorder='big') + data


def parse_ack(data: bytes):
    ack_seq = int.from_bytes(data[:SEQ_ID_SIZE], signed=True, byteorder='big')
    msg = data[SEQ_ID_SIZE:].decode('utf-8', errors='ignore')
    return ack_seq, msg


def run_sender():
    if not os.path.exists(FILE_PATH):
        return 0.0, 0.0, 0.0

    # handle empty file case
    packets = {}
    curr_seq = 0
    with open(FILE_PATH, 'rb') as f:
        while True:
            chunk = f.read(MESSAGE_SIZE)
            if not chunk:
                break
            packets[curr_seq] = chunk
            curr_seq += len(chunk)

    total_bytes = curr_seq
    seqs = sorted(packets.keys())  # packet boundary list

    # setup socket for UDP communication
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))     
    sock.setblocking(False)

    # throughput timer right after the socket setup
    start_time = time.time()     

    # the base and the right edge of the window 
    base = 0
    next_seq_num = 0

    send_times = {}      
    packet_delays = []  
    last_progress_time = time.time()

    # loop for sending packets in the sliding window until all bytes are acknowledged
    while base < total_bytes:
        # allow up to WINDOW_SIZE. Unless it's reaches the end of the file. 
        window_right = base + (WINDOW_SIZE * MESSAGE_SIZE)
        while next_seq_num < total_bytes and next_seq_num < window_right:
            pkt = create_packet(next_seq_num, packets[next_seq_num])
            sock.sendto(pkt, (RECEIVER_IP, RECEIVER_PORT))

            if next_seq_num not in send_times:
                send_times[next_seq_num] = time.time()

            next_seq_num += len(packets[next_seq_num])

        # process cumulative acks and update base. 
        try:
            ready = select.select([sock], [], [], 0.01)
            if ready[0]:
                data, _ = sock.recvfrom(PACKET_SIZE)
                ack_seq, _ = parse_ack(data)
                if ack_seq > base:
                    old_base = base
                    now = time.time()

                    # record delays for newly acked packets
                    for s in seqs:
                        if s < old_base:
                            continue
                        end = s + len(packets[s])
                        if end <= ack_seq:
                            if s in send_times:
                                packet_delays.append(now - send_times[s])
                                del send_times[s]
                        else:
                            break

                    base = ack_seq
                    last_progress_time = now

        except (BlockingIOError, OSError):
            pass

        # handle timeout and retransmit base packet go back N style
        if time.time() - last_progress_time > TIMEOUT:
            if base < total_bytes:
                pkt = create_packet(base, packets[base])
                sock.sendto(pkt, (RECEIVER_IP, RECEIVER_PORT))
                last_progress_time = time.time()

    # stop throughput timer after all ack
    ack_all_time = time.time()

    # send empty packet with seq_id = total_bytes to signal end of transmission
    fin_received = False
    for _ in range(10):
        sock.sendto(create_packet(total_bytes, b''), (RECEIVER_IP, RECEIVER_PORT))
        try:
            ready = select.select([sock], [], [], 0.5)
            if ready[0]:
                data, _ = sock.recvfrom(PACKET_SIZE)
                _, msg = parse_ack(data)
                if msg == 'fin':
                    fin_received = True
                    break
        except Exception:
            pass

    sock.sendto(create_packet(total_bytes, b'==FINACK=='), (RECEIVER_IP, RECEIVER_PORT))
    sock.close()

    # metrics calculation for output
    duration = ack_all_time - start_time
    throughput = (total_bytes / duration) if duration > 0 else 0.0

    avg_delay = (sum(packet_delays) / len(packet_delays)) if packet_delays else 0.0

    metric = (0.3 * (throughput / 1000.0)) + (0.7 / avg_delay) if avg_delay > 0 else 0.0

    return throughput, avg_delay, metric


if __name__ == "__main__":
    tp, d, m = run_sender()
    print(f"{tp:.7f},{d:.7f},{m:.7f}")
