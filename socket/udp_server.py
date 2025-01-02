import socket
import os
import hashlib
import threading
from queue import Queue
import time

BUFFER_SIZE = 1024
CHUNK_SIZE = 1024 * 32
SERVER_PORT = 1234
SERVER_IP = '192.168.1.18'
ENCODING = 'utf-8'
MAX_THREADS = 5


class FileServer:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((SERVER_IP, SERVER_PORT))
        self.available_files = {}
        self.current_client = None
        self.chunk_queue = Queue()

    def convert_size(self, size_str):
        units = {
            'B': 1,
            'KB': 1024,
            'MB': 1024 * 1024,
            'GB': 1024 * 1024 * 1024
        }
        size = size_str.strip()
        if not any(unit in size for unit in units):
            return int(size)

        number = float(''.join(filter(lambda x: x.isdigit() or x == '.', size)))
        unit = ''.join(filter(lambda x: x.isalpha(), size)).upper()

        return int(number * units[unit])

    def read_available_files(self):
        with open('files.txt', 'r') as f:
            lines = f.readlines()

        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2:
                filename, size = parts[0], parts[1]
                self.available_files[filename] = self.convert_size(size)

        print('Available files:')
        for filename, size in self.available_files.items():
            print(f"{filename}: {size} bytes")

    def calculate_checksum(self, data):
        return hashlib.md5(data).hexdigest()

    def send_chunk(self, chunk_num, chunk_data, client_addr):
        try:
            checksum = self.calculate_checksum(chunk_data)
            header = f"{chunk_num}|{len(chunk_data)}|{checksum}".encode()
            packet = header + b'|' + chunk_data
            self.sock.sendto(packet, client_addr)
            time.sleep(0.001)  # Small delay to prevent network congestion
            return True
        except Exception as e:
            print(f"Error sending chunk {chunk_num}: {e}")
            return False

    def transfer_file(self, filename, client_addr):
        if filename not in self.available_files:
            self.sock.sendto(b"FILE_NOT_FOUND", client_addr)
            return

        try:
            file_size = self.available_files[filename]
            total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

            # Send file info
            file_info = f"FILE_INFO|{filename}|{total_chunks}".encode()
            self.sock.sendto(file_info, client_addr)
            time.sleep(0.1)  # Wait for client to prepare

            # Read and send file chunks
            with open(filename, 'rb') as f:
                for chunk_num in range(total_chunks):
                    chunk_data = f.read(CHUNK_SIZE)
                    if not chunk_data:
                        break

                    # Try sending chunk up to 3 times
                    for _ in range(3):
                        if self.send_chunk(chunk_num, chunk_data, client_addr):
                            break
                        time.sleep(0.1)

            print(f"Finished sending {filename} to {client_addr}")

        except FileNotFoundError:
            self.sock.sendto(b"FILE_NOT_FOUND", client_addr)
        except Exception as e:
            print(f"Error transferring file: {e}")
            self.sock.sendto(b"TRANSFER_ERROR", client_addr)

    def handle_missing_chunks(self, data, client_addr):
        try:
            _, file_info = data.decode().split(":", 1)
            filename, chunks = file_info.split("|")
            missing_chunks = [int(c) for c in chunks.split(",")]

            if filename not in self.available_files:
                return

            with open(filename, 'rb') as f:
                for chunk_num in missing_chunks:
                    f.seek(chunk_num * CHUNK_SIZE)
                    chunk_data = f.read(CHUNK_SIZE)
                    if chunk_data:
                        self.send_chunk(chunk_num, chunk_data, client_addr)
                        time.sleep(0.01)  # Small delay between retransmissions
        except Exception as e:
            print(f"Error handling missing chunks: {e}")

    def handle_client(self):
        while True:
            try:
                data, client_addr = self.sock.recvfrom(BUFFER_SIZE)

                if not self.current_client:
                    self.current_client = client_addr
                elif client_addr != self.current_client:
                    self.sock.sendto(b"BUSY", client_addr)
                    continue

                message = data.decode()

                if message == "REQUEST_FILES":
                    # Send available files list
                    files_list = "|".join(f"{name}:{size}" for name, size in self.available_files.items())
                    self.sock.sendto(files_list.encode(), client_addr)

                elif message.startswith("DOWNLOAD:"):
                    filename = message.split(":")[1]
                    self.transfer_file(filename, client_addr)

                elif message.startswith("MISSING_CHUNKS:"):
                    self.handle_missing_chunks(data, client_addr)

                elif message == "DISCONNECT":
                    self.sock.sendto(b"GOODBYE", client_addr)
                    if client_addr == self.current_client:
                        self.current_client = None

            except Exception as e:
                print(f"Error handling client: {e}")
                continue

    def start(self):
        self.read_available_files()
        print(f"Server started on {SERVER_IP}:{SERVER_PORT}")
        try:
            self.handle_client()
        except KeyboardInterrupt:
            print("\nServer shutting down...")
            if self.current_client:
                self.sock.sendto(b"SERVER_SHUTDOWN", self.current_client)


if __name__ == "__main__":
    server = FileServer()
    server.start()