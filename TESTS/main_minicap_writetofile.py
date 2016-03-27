import socket
import struct

def parseGlobalHeader(data):
    vers = struct.unpack_from("B", data, 0)[0]
    print("VERSION =", vers)

    header_size = struct.unpack_from("B", data, 1)[0]
    print("H SIZE =", header_size)

    proc_pid = struct.unpack_from("I", data, 2)[0]
    print("PID =", proc_pid)

    x_real = struct.unpack_from("I", data, 6)[0]
    y_real = struct.unpack_from("I", data, 10)[0]
    print("Real display size: ", x_real, "x", y_real)

    x_virt = struct.unpack_from("I", data, 14)[0]
    y_virt = struct.unpack_from("I", data, 18)[0]
    print("Real display size: ", x_virt, "x", y_virt)

    disp_or = struct.unpack_from("B", data, 22)[0]
    print("ORIENTATION =", disp_or)
    qirks = struct.unpack_from("B", data, 23)[0]
    print("qirks =", qirks)


TCP_IP = '127.0.0.1'
TCP_PORT = 1313
BUFFER_SIZE = 10000

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((TCP_IP, TCP_PORT))
out = open("tmp.jpg", "wb")

data = sock.recv(24)
parseGlobalHeader(data)

try:
    while True:
        data = sock.recv(4)
        frame_size = struct.unpack_from("I", data, 0)[0]

        frame = b""
        while len(frame) < frame_size:
            data = sock.recv(4096)
            print(frame_size, len(frame))
            frame += data

        out.write(frame)

except KeyboardInterrupt:
    sock.close()

