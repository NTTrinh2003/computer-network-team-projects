# client_gui.py
import tkinter as tk
from tkinter import ttk, messagebox
import json
import socket
import threading
import os
from datetime import datetime
from threading import Thread
import time

class DownloadManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Download Manager")
        self.root.geometry("800x600")
        
        # Server connection details
        self.host = 'localhost'
        self.port = 5000
        self.files_info = {}
        self.active_downloads = {}
        self.downloaded_files = set()
        
        # Thêm thư mục downloads
        self.download_dir = "downloads"
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
        
        self.setup_gui()
        self.connect_to_server()
        
        # Bắt đầu thread monitor input.txt
        self.monitor_thread = threading.Thread(target=self.monitor_input_file)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
    def setup_gui(self):
        """Setup the GUI layout"""
        # Create main frames
        self.setup_available_files_frame()
        self.setup_downloads_frame()
        self.setup_status_bar()
        
    def setup_available_files_frame(self):
        """Setup the available files list frame"""
        frame = ttk.LabelFrame(self.root, text="Available Files", padding="5")
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create treeview for files list
        columns = ("File", "Size", "Status")
        self.files_tree = ttk.Treeview(frame, columns=columns, show='headings')
        
        # Setup columns
        for col in columns:
            self.files_tree.heading(col, text=col)
            self.files_tree.column(col, width=150)
            
        # Add scrollbar
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.files_tree.yview)
        self.files_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack elements
        self.files_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Add download button
        self.download_btn = ttk.Button(frame, text="Download Selected", command=self.start_download)
        self.download_btn.pack(pady=5)
        
    def setup_downloads_frame(self):
        """Setup the active downloads frame"""
        frame = ttk.LabelFrame(self.root, text="Active Downloads", padding="5")
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create treeview for downloads
        columns = ("File", "Progress", "Speed", "Status")
        self.downloads_tree = ttk.Treeview(frame, columns=columns, show='headings')
        
        # Setup columns
        for col in columns:
            self.downloads_tree.heading(col, text=col)
            self.downloads_tree.column(col, width=150)
            
        # Add scrollbar
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.downloads_tree.yview)
        self.downloads_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack elements
        self.downloads_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
    def setup_status_bar(self):
        """Setup the status bar"""
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, padx=5, pady=5)
        self.status_var.set("Ready")
        
    def connect_to_server(self):
        """Connect to server and get files list"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)  # Thêm timeout 5 giây
            sock.connect((self.host, self.port))
            
            # Get files list
            files_data = sock.recv(4096).decode()
            self.files_info = json.loads(files_data)
            sock.close()
            
            # Update GUI
            self.update_files_list()
            self.status_var.set("Connected to server")
            
        except ConnectionRefusedError:
            error_msg = "Không thể kết nối đến server. Hãy đảm bảo server đang chạy."
            messagebox.showerror("Lỗi Kết Nối", error_msg)
            self.status_var.set("Kết nối thất bại - Server không hoạt động")
        except socket.timeout:
            error_msg = "Kết nối đến server quá thời gian chờ"
            messagebox.showerror("Lỗi Kết Nối", error_msg)
            self.status_var.set("Kết nối thất bại - Timeout")
        except Exception as e:
            error_msg = f"Lỗi kết nối đến server: {str(e)}"
            messagebox.showerror("Lỗi Kết Nối", error_msg)
            self.status_var.set("Kết nối thất bại")
            
    def update_files_list(self):
        """Update the available files list in GUI"""
        # Clear existing items
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
            
        # Add files from server
        for filename, size in self.files_info.items():
            status = "Downloaded" if filename in self.downloaded_files else "Available"
            size_str = self.format_size(size)
            self.files_tree.insert('', tk.END, values=(filename, size_str, status))
            
    def format_size(self, size_bytes):
        """Format file size to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"
        
    def start_download(self, filename):
        """Bắt đầu download file với 4 threads"""
        try:
            file_size = self.files_info[filename]
            chunk_size = file_size // 4
            threads = []
            self.download_progress = {filename: 0}

            # Tạo đường dẫn đầy đủ cho file
            full_path = os.path.join(self.download_dir, filename)
            
            for i in range(4):
                start = i * chunk_size
                end = file_size if i == 3 else (i + 1) * chunk_size
                
                thread = Thread(
                    target=self.download_chunk,
                    args=(filename, start, end, i, full_path)
                )
                threads.append(thread)
                thread.start()

            # Chờ tất cả threads hoàn thành
            for thread in threads:
                thread.join()

            # Ghép các phần file lại
            self.merge_file_chunks(filename)
            
            # Cập nhật trạng thái
            self.downloaded_files.add(filename)
            self.update_gui()

        except Exception as e:
            print(f"Lỗi download {filename}: {str(e)}")

    def download_chunk(self, filename, start, end, chunk_id, full_path):
        """Download một phần của file"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.host, self.port))

            request = {
                'filename': filename,
                'start': start,
                'end': end
            }
            sock.send(json.dumps(request).encode())

            # Tạo temporary file trong thư mục downloads
            temp_filename = f"{full_path}.part{chunk_id}"
            received_bytes = 0
            chunk_size = end - start

            with open(temp_filename, 'wb') as f:
                while received_bytes < chunk_size:
                    data = sock.recv(min(4096, chunk_size - received_bytes))
                    if not data:
                        break
                    f.write(data)
                    received_bytes += len(data)
                    
                    # Cập nhật tiến độ
                    progress = (received_bytes / chunk_size) * 25  # 25% cho mỗi chunk
                    self.update_progress(filename, chunk_id, progress)

        except Exception as e:
            print(f"Lỗi download chunk {chunk_id} của {filename}: {str(e)}")
        finally:
            sock.close()

    def merge_file_chunks(self, filename):
        """Ghép các phần file lại với nhau"""
        try:
            full_path = os.path.join(self.download_dir, filename)
            with open(full_path, 'wb') as outfile:
                for i in range(4):
                    chunk_name = f"{full_path}.part{i}"
                    with open(chunk_name, 'rb') as infile:
                        outfile.write(infile.read())
                    os.remove(chunk_name)  # Xóa file tạm
        except Exception as e:
            print(f"Lỗi ghép file {filename}: {str(e)}")

    def update_progress(self, filename, chunk_id, chunk_progress):
        """Cập nhật tiến độ download"""
        with threading.Lock():
            current_progress = self.download_progress[filename]
            # Cập nhật phần progress của chunk này (mỗi chunk 25%)
            base_progress = chunk_id * 25
            chunk_contribution = chunk_progress
            new_progress = min(100, current_progress + chunk_contribution)
            self.download_progress[filename] = new_progress
            
            # Cập nhật GUI
            self.update_download_progress(filename, new_progress)

    def update_download_progress(self, filename, progress):
        """Cập nhật tiến độ trên GUI"""
        for item in self.downloads_tree.get_children():
            if self.downloads_tree.item(item)['values'][0] == filename:
                self.downloads_tree.set(item, 'Progress', f"{progress:.1f}%")
                self.downloads_tree.set(item, 'Status', 'Downloading' if progress < 100 else 'Completed')
                break

    def update_gui(self):
        """Update the GUI"""
        self.update_files_list()
        self.status_var.set("Download completed")
        
    def monitor_input_file(self):
        """Kiểm tra file input.txt mỗi 5 giây"""
        processed_files = set()  # Lưu các file đã xử lý
        
        while True:
            try:
                # Đọc danh sách file từ input.txt
                with open('input.txt', 'r') as f:
                    files = set(f.read().splitlines())
                
                # Tìm các file mới chưa xử lý
                new_files = files - processed_files
                
                # Download các file mới
                for filename in new_files:
                    if filename in self.files_info:  # Kiểm tra file có tồn tại trên server
                        self.start_download(filename)
                        processed_files.add(filename)  # Đánh dấu đã xử lý
                
                time.sleep(5)  # Đợi 5 giây trước khi kiểm tra lại
                
            except Exception as e:
                print(f"Lỗi khi đọc input.txt: {str(e)}")
                time.sleep(5)
        
# main_client_gui.py
if __name__ == "__main__":
    root = tk.Tk()
    app = DownloadManagerGUI(root)
    root.mainloop()