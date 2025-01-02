import socket
import os
import hashlib
import threading
import time
import sys

BUFFER_SIZE = 1024
CHUNK_SIZE = 1024 * 32
SERVER_PORT = 1234
SERVER_IP = '192.168.1.18'
MAX_THREADS = 5


class ProgressBar:
    def __init__(self, total, prefix=''):
        self.total = total
        self.prefix = prefix
        self.current = 0
        self.start_time = time.time()
        self.lock = threading.Lock()

    def update(self, current):
        with self.lock:
            self.current = current
            self.draw()

    def draw(self):
        progress = self.current / self.total
        percentage = progress * 100

        elapsed_time = time.time() - self.start_time
        speed = self.current / elapsed_time if elapsed_time > 0 else 0
        eta = (self.total - self.current) / speed if speed > 0 else 0

        # Only show filename, percentage and ETA
        sys.stdout.write('\r')
        sys.stdout.write(f'{self.prefix}: {percentage:3.0f}% (ETA: {eta:.0f}s)')
        sys.stdout.flush()

        if self.current == self.total:
            sys.stdout.write('\n')


class FileClient:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(5.0)  # Set socket timeout
        self.server_addr = (SERVER_IP, SERVER_PORT)
        self.received_chunks = {}
        self.missing_chunks = set()
        self.current_file = None
        self.total_chunks = 0
        self.progress_bar = None
        self.lock = threading.Lock()

    def calculate_checksum(self, data):
        return hashlib.md5(data).hexdigest()

    def read_request_files(self):
        with open('input.txt', 'r') as f:
            return [line.strip() for line in f.readlines()]

    def verify_chunk(self, chunk_num, chunk_data, received_checksum):
        calculated_checksum = self.calculate_checksum(chunk_data)
        return calculated_checksum == received_checksum

    def receive_file_chunk(self):
        while True:
            try:
                data, _ = self.sock.recvfrom(CHUNK_SIZE + 1024)

                # Split packet into header and data
                try:
                    header_end = data.index(b'|', data.index(b'|', data.index(b'|') + 1) + 1) + 1
                    header = data[:header_end - 1].decode()
                    chunk_data = data[header_end:]

                    chunk_num, chunk_size, checksum = header.split('|')
                    chunk_num = int(chunk_num)
                    chunk_size = int(chunk_size)

                    if self.verify_chunk(chunk_num, chunk_data, checksum):
                        with self.lock:
                            self.received_chunks[chunk_num] = chunk_data
                            if chunk_num in self.missing_chunks:
                                self.missing_chunks.remove(chunk_num)
                        if self.progress_bar:
                            self.progress_bar.update(len(self.received_chunks))
                    else:
                        self.missing_chunks.add(chunk_num)

                    if len(self.received_chunks) == self.total_chunks:
                        break

                except (ValueError, IndexError) as e:
                    print(f"\nError parsing chunk: {e}")
                    continue

            except socket.timeout:
                break
            except Exception as e:
                print(f"\nError receiving chunk: {e}")
                break

    def request_missing_chunks(self):
        missing = set(range(self.total_chunks)) - set(self.received_chunks.keys())
        if missing:
            self.missing_chunks = missing
            chunks_str = ",".join(map(str, missing))
            message = f"MISSING_CHUNKS:{self.current_file}|{chunks_str}"
            self.sock.sendto(message.encode(), self.server_addr)
            return True
        return False

    def save_file(self, filename):
        if not self.received_chunks:
            return False

        try:
            # Create downloads directory if it doesn't exist
            downloads_dir = "downloads"
            if not os.path.exists(downloads_dir):
                os.makedirs(downloads_dir)

            # Save file in downloads directory
            file_path = os.path.join(downloads_dir, f"{filename}")
            with open(file_path, 'wb') as f:
                for chunk_num in range(self.total_chunks):
                    if chunk_num in self.received_chunks:
                        f.write(self.received_chunks[chunk_num])
            return True
        except Exception as e:
            print(f"\nError saving file: {e}")
            return False

    def download_file(self, filename):
        self.current_file = filename
        self.received_chunks.clear()
        self.missing_chunks.clear()

        # Request file download
        self.sock.sendto(f"DOWNLOAD:{filename}".encode(), self.server_addr)

        try:
            # Receive file info
            data, _ = self.sock.recvfrom(BUFFER_SIZE)
            response = data.decode()

            if response == "FILE_NOT_FOUND":
                print(f"File {filename} not found on server")
                return False

            try:
                _, _, total_chunks = response.split("|")
                self.total_chunks = int(total_chunks)
            except (ValueError, IndexError):
                print("Invalid file info received")
                return False

            # Initialize progress bar
            self.progress_bar = ProgressBar(
                total=self.total_chunks,
                prefix=f"Downloading {filename}"
            )

            # Start receiving threads
            receive_threads = []
            for _ in range(MAX_THREADS):
                thread = threading.Thread(target=self.receive_file_chunk)
                thread.start()
                receive_threads.append(thread)

            # Wait for threads to complete
            for thread in receive_threads:
                thread.join()

            # Request missing chunks up to 3 times
            retries = 0
            while self.request_missing_chunks() and retries < 3:
                self.receive_file_chunk()
                retries += 1

            if len(self.received_chunks) == self.total_chunks:
                print(f"\nDownload completed: {filename}")
                return self.save_file(filename)
            else:
                print(f"\nDownload incomplete: {filename} ({len(self.received_chunks)}/{self.total_chunks} chunks)")
                return False

        except socket.timeout:
            print(f"\nTimeout while downloading {filename}")
            return False
        except Exception as e:
            print(f"\nError downloading file: {e}")
            return False

    def start(self):
        try:
            # Request available files
            self.sock.sendto(b"REQUEST_FILES", self.server_addr)
            data, _ = self.sock.recvfrom(BUFFER_SIZE)
            available_files = dict(f.split(":") for f in data.decode().split("|"))
            print("Available files:", available_files)

            # Read requested files
            request_files = self.read_request_files()
            print("Requested files:", request_files)

            # Download each requested file
            for filename in request_files:
                if filename in available_files:
                    print(f"\nStarting download of {filename}...")
                    if self.download_file(filename):
                        print(f"Successfully downloaded {filename}")
                    else:
                        print(f"Failed to download {filename}")
                else:
                    print(f"File {filename} not available on server")

            # Disconnect from server
            self.sock.sendto(b"DISCONNECT", self.server_addr)

        except Exception as e:
            print(f"Error: {e}")
        finally:
            self.sock.close()


if __name__ == "__main__":
    client = FileClient()
    client.start()