# server.py
import socket
import json
import os
from threading import Thread
import logging

# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class FileServer:
    def __init__(self, host='localhost', port=5000):
        self.host = host
        self.port = port
        self.files_info = {}
        self.server = None
        self.load_files_info()
        
    def load_files_info(self):
        """Load file information from files.txt"""
        try:
            if not os.path.exists('files.txt'):
                logging.error("files.txt không tồn tại!")
                self.create_sample_files_txt()
                
            with open('files.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        filename, size = line.strip().split()
                        if os.path.exists(filename):
                            self.files_info[filename] = self._convert_size_to_bytes(size)
                        else:
                            logging.warning(f"File {filename} không tồn tại trong thư mục")
                    except ValueError:
                        logging.error(f"Định dạng không hợp lệ trong files.txt: {line}")
                        
            if not self.files_info:
                logging.warning("Không có file nào được tải lên!")
                
        except Exception as e:
            logging.error(f"Lỗi khi đọc files.txt: {str(e)}")
            
    def create_sample_files_txt(self):
        """Tạo file files.txt mẫu"""
        sample_content = "example.txt 1MB\ntest.pdf 5MB"
        try:
            with open('files.txt', 'w', encoding='utf-8') as f:
                f.write(sample_content)
            logging.info("Đã tạo files.txt mẫu")
        except Exception as e:
            logging.error(f"Không thể tạo files.txt mẫu: {str(e)}")
    
    def start(self):
        """Start the server"""
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((self.host, self.port))
            self.server.listen(5)
            logging.info(f"Server đang chạy tại {self.host}:{self.port}")
            logging.info(f"Danh sách files có sẵn: {list(self.files_info.keys())}")
            
            while True:
                client_socket, address = self.server.accept()
                logging.info(f"Kết nối mới từ {address}")
                client_thread = Thread(target=self.handle_client, args=(client_socket,))
                client_thread.daemon = True
                client_thread.start()
                
        except OSError as e:
            if e.errno == 98:  # Port đã được sử dụng
                logging.error(f"Port {self.port} đã được sử dụng")
            else:
                logging.error(f"Lỗi khởi động server: {str(e)}")
        except KeyboardInterrupt:
            logging.info("Đang tắt server...")
        except Exception as e:
            logging.error(f"Lỗi không mong đợi: {str(e)}")
        finally:
            if self.server:
                self.server.close()
                
    def stop(self):
        """Stop the server gracefully"""
        if self.server:
            self.server.close()
            logging.info("Server đã dừng")

    def handle_client(self, client_socket):
        """Xử lý kết nối từ client"""
        try:
            # Gửi danh sách files cho client
            files_data = json.dumps(self.files_info)
            client_socket.send(files_data.encode())

            # Nhận request download từ client
            while True:
                request_data = client_socket.recv(4096).decode()
                if not request_data:
                    break
                
                request = json.loads(request_data)
                filename = request.get('filename')
                start = request.get('start', 0)
                end = request.get('end')

                if filename not in self.files_info:
                    logging.error(f"File {filename} không tồn tại")
                    continue

                # Đọc và gửi phần được yêu cầu của file
                try:
                    with open(filename, 'rb') as f:
                        f.seek(start)
                        # Nếu end không được chỉ định, gửi toàn bộ file
                        if end is None:
                            data = f.read()
                        else:
                            data = f.read(end - start)
                        client_socket.sendall(data)
                    logging.info(f"Đã gửi {filename} từ byte {start} đến {end}")
                except FileNotFoundError:
                    logging.error(f"Không tìm thấy file {filename}")
                except Exception as e:
                    logging.error(f"Lỗi khi đọc file {filename}: {str(e)}")

        except json.JSONDecodeError:
            logging.error("Lỗi decode JSON từ client")
        except Exception as e:
            logging.error(f"Lỗi không mong đợi: {str(e)}")
        finally:
            client_socket.close()

    def _convert_size_to_bytes(self, size_str):
        """Chuyển đổi kích thước từ dạng chuỗi (VD: '1MB') sang bytes"""
        units = {
            'B': 1,
            'KB': 1024,
            'MB': 1024 * 1024,
            'GB': 1024 * 1024 * 1024,
            'TB': 1024 * 1024 * 1024 * 1024
        }
        
        # Tách số và đơn vị
        size = size_str.strip()
        if not any(unit in size for unit in units):
            return int(size)
        
        number = float(''.join(filter(lambda x: x.isdigit() or x == '.', size)))
        unit = ''.join(filter(lambda x: x.isalpha(), size)).upper()
        
        if unit not in units:
            raise ValueError(f"Đơn vị không hợp lệ: {unit}")
        
        return int(number * units[unit])

if __name__ == "__main__":
    server = FileServer()
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()