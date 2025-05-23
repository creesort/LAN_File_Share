#!/usr/bin/env python3
"""
LAN File Transfer Application
A GUI-based tool for sending and receiving files over local network
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import socket
import threading
import os
import json
import time
import subprocess
import platform
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import shutil
import tempfile
from datetime import datetime
import requests
import zipfile

class FileTransferServer(BaseHTTPRequestHandler):
    """HTTP server for handling file transfers"""
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/':
            self.send_main_page()
        elif self.path == '/upload':
            self.send_upload_page()
        elif self.path.startswith('/download/'):
            self.handle_download()
        elif self.path == '/status':
            self.send_status()
        else:
            self.send_404()
    
    def do_POST(self):
        """Handle POST requests for file uploads"""
        if self.path == '/upload':
            self.handle_upload()
        else:
            self.send_404()
    
    def send_main_page(self):
        """Send the main page HTML"""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>File Transfer</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
                .container { max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                .btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 5px; text-decoration: none; display: inline-block; }
                .btn:hover { background: #0056b3; }
                .file-list { margin: 20px 0; }
                .file-item { background: #f8f9fa; padding: 10px; margin: 5px 0; border-radius: 5px; }
                .upload-area { border: 2px dashed #ccc; padding: 20px; text-align: center; margin: 20px 0; }
                .status { margin: 10px 0; padding: 10px; border-radius: 5px; }
                .success { background: #d4edda; color: #155724; }
                .error { background: #f8d7da; color: #721c24; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>File Transfer Hub</h1>
                <p>Welcome! You can upload files to share or download available files.</p>
                
                <div class="upload-area">
                    <h3>Upload Files</h3>
                    <form action="/upload" method="post" enctype="multipart/form-data">
                        <input type="file" name="file" multiple style="margin: 10px;">
                        <br>
                        <button type="submit" class="btn">Upload Files</button>
                    </form>
                </div>
                
                <div class="file-list">
                    <h3>Available Files (Shared Space)</h3>
                    <div id="files">Loading...</div>
                </div>
                
                <script>
                    function loadFiles() {
                        fetch('/status')
                            .then(response => response.json())
                            .then(data => {
                                const filesDiv = document.getElementById('files');
                                if (data.files.length === 0) {
                                    filesDiv.innerHTML = '<p>No files available for download.</p>';
                                } else {
                                    filesDiv.innerHTML = data.files.map(file => 
                                        `<div class="file-item">
                                            <strong>${file.name}</strong> (${formatSize(file.size)})
                                            <a href="/download/${encodeURIComponent(file.name)}" class="btn" style="float: right;">Download</a>
                                        </div>`
                                    ).join('');
                                }
                            })
                            .catch(err => {
                                document.getElementById('files').innerHTML = '<p class="error">Error loading files.</p>';
                            });
                    }
                    
                    function formatSize(bytes) {
                        if (bytes === 0) return '0 Bytes';
                        const k = 1024;
                        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
                        const i = Math.floor(Math.log(bytes) / Math.log(k));
                        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
                    }
                    
                    loadFiles();
                    setInterval(loadFiles, 3000); // Refresh every 3 seconds
                </script>
            </div>
        </body>
        </html>
        """
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def handle_upload(self):
        """Handle file upload"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            # Parse multipart form data
            boundary = self.headers['Content-Type'].split('boundary=')[1]
            parts = post_data.split(f'--{boundary}'.encode())
            
            for part in parts:
                if b'filename=' in part:
                    # Extract filename
                    filename_start = part.find(b'filename="') + 10
                    filename_end = part.find(b'"', filename_start)
                    filename = part[filename_start:filename_end].decode()
                    
                    if filename:
                        # Extract file content
                        file_start = part.find(b'\r\n\r\n') + 4
                        file_end = part.rfind(b'\r\n')
                        file_content = part[file_start:file_end]
                        
                        # Save file
                        safe_filename = os.path.basename(filename)
                        filepath = os.path.join(self.server.shared_folder, safe_filename)
                        
                        with open(filepath, 'wb') as f:
                            f.write(file_content)
                        
                        # Update server's file list
                        if hasattr(self.server, 'app'):
                            self.server.app.update_status(f"Received file: {safe_filename}")
            
            # Send success response
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            error_html = f"<h1>Upload Error</h1><p>{str(e)}</p><a href='/'>Go Back</a>"
            self.wfile.write(error_html.encode())
    
    def handle_download(self):
        """Handle file download"""
        try:
            filename = urllib.parse.unquote(self.path.split('/download/')[1])
            filepath = os.path.join(self.server.shared_folder, filename)
            
            if os.path.exists(filepath) and os.path.isfile(filepath):
                self.send_response(200)
                self.send_header('Content-type', 'application/octet-stream')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Content-Length', str(os.path.getsize(filepath)))
                self.end_headers()
                
                with open(filepath, 'rb') as f:
                    shutil.copyfileobj(f, self.wfile)
                
                if hasattr(self.server, 'app'):
                    self.server.app.update_status(f"File downloaded: {filename}")
            else:
                self.send_404()
                
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            error_html = f"<h1>Download Error</h1><p>{str(e)}</p>"
            self.wfile.write(error_html.encode())
    
    def send_status(self):
        """Send current status as JSON"""
        try:
            files = []
            if hasattr(self.server, 'shared_folder'):
                for filename in os.listdir(self.server.shared_folder):
                    filepath = os.path.join(self.server.shared_folder, filename)
                    if os.path.isfile(filepath):
                        files.append({
                            'name': filename,
                            'size': os.path.getsize(filepath)
                        })
            
            response = {'files': files}
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_response(500)
            self.end_headers()
    
    def send_404(self):
        """Send 404 error"""
        self.send_response(404)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        html = "<h1>404 - Page Not Found</h1><a href='/'>Go Home</a>"
        self.wfile.write(html.encode())
    
    def log_message(self, format, *args):
        """Override to suppress server logs"""
        pass

class FileTransferApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LAN File Transfer")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # Variables
        self.server = None
        self.server_thread = None
        self.ngrok_process = None
        self.shared_folder = tempfile.mkdtemp(prefix="file_transfer_")
        self.discovered_devices = []
        
        # Setup GUI
        self.setup_gui()
        
        # Get local IP
        self.local_ip = self.get_local_ip()
        self.port = 8000
        
        # Start server automatically
        self.start_server()
    
    def setup_gui(self):
        """Setup the GUI components"""
        # Main notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Tab 1: Device Discovery & File Transfer
        transfer_frame = ttk.Frame(notebook)
        notebook.add(transfer_frame, text="File Transfer")
        
        # Device Discovery Section
        discovery_frame = ttk.LabelFrame(transfer_frame, text="Device Discovery", padding=10)
        discovery_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Button(discovery_frame, text="🔍 Scan Network", 
                  command=self.scan_devices).pack(side='left', padx=(0, 10))
        
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(discovery_frame, textvariable=self.device_var, 
                                        state='readonly', width=30)
        self.device_combo.pack(side='left', padx=(0, 10))
        
        ttk.Button(discovery_frame, text="📤 Send File", 
                  command=self.send_file_to_device).pack(side='left', padx=(0, 5))
        ttk.Button(discovery_frame, text="📥 Request File", 
                  command=self.request_file_from_device).pack(side='left')
        
        # Local Server Section
        server_frame = ttk.LabelFrame(transfer_frame, text="Local Server", padding=10)
        server_frame.pack(fill='x', pady=(0, 10))
        
        self.server_status = tk.StringVar(value="Server: Stopped")
        ttk.Label(server_frame, textvariable=self.server_status).pack(anchor='w')
        
        self.server_url = tk.StringVar()
        url_frame = ttk.Frame(server_frame)
        url_frame.pack(fill='x', pady=(5, 0))
        
        ttk.Label(url_frame, text="Local URL:").pack(side='left')
        url_entry = ttk.Entry(url_frame, textvariable=self.server_url, state='readonly')
        url_entry.pack(side='left', fill='x', expand=True, padx=(5, 5))
        
        ttk.Button(url_frame, text="📋 Copy", 
                  command=self.copy_url).pack(side='right', padx=(0, 5))
        ttk.Button(url_frame, text="🌐 Open", 
                  command=self.open_url).pack(side='right')
        
        # Internet Sharing Section
        internet_frame = ttk.LabelFrame(transfer_frame, text="Internet Sharing (ngrok)", padding=10)
        internet_frame.pack(fill='x', pady=(0, 10))
        
        self.ngrok_status = tk.StringVar(value="ngrok: Not active")
        ttk.Label(internet_frame, textvariable=self.ngrok_status).pack(anchor='w')
        
        self.ngrok_url = tk.StringVar()
        ngrok_url_frame = ttk.Frame(internet_frame)
        ngrok_url_frame.pack(fill='x', pady=(5, 0))
        
        ttk.Label(ngrok_url_frame, text="Public URL:").pack(side='left')
        ngrok_entry = ttk.Entry(ngrok_url_frame, textvariable=self.ngrok_url, state='readonly')
        ngrok_entry.pack(side='left', fill='x', expand=True, padx=(5, 5))
        
        ttk.Button(ngrok_url_frame, text="📋 Copy", 
                  command=self.copy_ngrok_url).pack(side='right', padx=(0, 5))
        ttk.Button(ngrok_url_frame, text="🌐 Open", 
                  command=self.open_ngrok_url).pack(side='right')
        
        ngrok_controls = ttk.Frame(internet_frame)
        ngrok_controls.pack(fill='x', pady=(5, 0))
        
        ttk.Button(ngrok_controls, text="🚀 Start ngrok", 
                  command=self.start_ngrok).pack(side='left', padx=(0, 5))
        ttk.Button(ngrok_controls, text="⏹️ Stop ngrok", 
                  command=self.stop_ngrok).pack(side='left')
        
        # File Management Section
        files_frame = ttk.LabelFrame(transfer_frame, text="Shared Files", padding=10)
        files_frame.pack(fill='both', expand=True)
        
        file_controls = ttk.Frame(files_frame)
        file_controls.pack(fill='x', pady=(0, 10))
        
        ttk.Button(file_controls, text="➕ Add Files", 
                  command=self.add_files).pack(side='left', padx=(0, 5))
        ttk.Button(file_controls, text="📁 Open Folder", 
                  command=self.open_shared_folder).pack(side='left', padx=(0, 5))
        ttk.Button(file_controls, text="🗑️ Clear All", 
                  command=self.clear_files).pack(side='left')
        
        # File list
        self.file_tree = ttk.Treeview(files_frame, columns=('Size', 'Modified'), show='tree headings')
        self.file_tree.heading('#0', text='File Name')
        self.file_tree.heading('Size', text='Size')
        self.file_tree.heading('Modified', text='Modified')
        self.file_tree.column('#0', width=300)
        self.file_tree.column('Size', width=100)
        self.file_tree.column('Modified', width=150)
        
        file_scroll = ttk.Scrollbar(files_frame, orient='vertical', command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=file_scroll.set)
        
        self.file_tree.pack(side='left', fill='both', expand=True)
        file_scroll.pack(side='right', fill='y')
        
        # Tab 2: Status & Logs
        status_frame = ttk.Frame(notebook)
        notebook.add(status_frame, text="Status & Logs")
        
        self.status_text = scrolledtext.ScrolledText(status_frame, height=20)
        self.status_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Add initial status
        self.update_status("Application started")
        self.update_status(f"Shared folder: {self.shared_folder}")
    
    def get_local_ip(self):
        """Get the local IP address"""
        try:
            # Connect to a remote server to get local IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except:
            return "127.0.0.1"
    
    def start_server(self):
        """Start the HTTP server"""
        try:
            self.server = HTTPServer((self.local_ip, self.port), FileTransferServer)
            self.server.shared_folder = self.shared_folder
            self.server.app = self
            
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            
            url = f"http://{self.local_ip}:{self.port}"
            self.server_url.set(url)
            self.server_status.set(f"Server: Running on {self.local_ip}:{self.port}")
            self.update_status(f"Server started: {url}")
            
        except Exception as e:
            self.update_status(f"Error starting server: {str(e)}")
            messagebox.showerror("Server Error", f"Failed to start server: {str(e)}")
    
    def scan_devices(self):
        """Scan for devices on the local network"""
        def scan_thread():
            self.update_status("Scanning network for devices...")
            devices = []
            
            # Get network range
            ip_parts = self.local_ip.split('.')
            network = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}"
            
            # Scan common ports
            for i in range(1, 255):
                if i == int(ip_parts[3]):  # Skip own IP
                    continue
                    
                target_ip = f"{network}.{i}"
                
                # Check if device responds on common HTTP ports
                for port in [80, 8000, 8080, 3000, 5000]:
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(0.1)
                        result = sock.connect_ex((target_ip, port))
                        sock.close()
                        
                        if result == 0:
                            devices.append(f"{target_ip}:{port}")
                            break
                    except:
                        continue
            
            # Update GUI in main thread
            self.root.after(0, self.update_device_list, devices)
        
        threading.Thread(target=scan_thread, daemon=True).start()
    
    def update_device_list(self, devices):
        """Update the device list in the GUI"""
        self.discovered_devices = devices
        self.device_combo['values'] = devices
        
        if devices:
            self.update_status(f"Found {len(devices)} devices: {', '.join(devices)}")
        else:
            self.update_status("No devices found on network")
    
    def send_file_to_device(self):
        """Send a file to selected device"""
        if not self.device_var.get():
            messagebox.showwarning("No Device", "Please select a device first")
            return
        
        files = filedialog.askopenfilenames(title="Select files to send")
        if not files:
            return
        
        device = self.device_var.get()
        self.update_status(f"Attempting to send files to {device}")
        
        # For now, show instructions to user
        message = f"""To send files to {device}:

1. Copy this URL and share it with the target device:
   {self.server_url.get()}

2. The other device can visit this URL to download your files.

Files ready to send: {', '.join(os.path.basename(f) for f in files)}"""

        # Copy files to shared folder
        for file_path in files:
            try:
                filename = os.path.basename(file_path)
                dest_path = os.path.join(self.shared_folder, filename)
                shutil.copy2(file_path, dest_path)
                self.update_status(f"Added file to share: {filename}")
            except Exception as e:
                self.update_status(f"Error copying file {filename}: {str(e)}")
        
        self.refresh_file_list()
        messagebox.showinfo("Files Ready", message)
    
    def request_file_from_device(self):
        """Request a file from selected device"""
        if not self.device_var.get():
            messagebox.showwarning("No Device", "Please select a device first")
            return
        
        device = self.device_var.get()
        url = f"http://{device}"
        
        message = f"""To request files from {device}:

1. Ask the other device to visit: {self.server_url.get()}
2. They can upload files through the web interface
3. Or try accessing their server at: {url}"""
        
        self.update_status(f"File request setup for {device}")
        messagebox.showinfo("File Request", message)
        
        # Try to open the device's potential server
        try:
            webbrowser.open(url)
        except:
            pass
    
    def start_ngrok(self):
        """Start ngrok tunnel"""
        def start_ngrok_thread():
            try:
                # Check if ngrok is installed
                result = subprocess.run(['ngrok', 'version'], capture_output=True, text=True)
                if result.returncode != 0:
                    self.root.after(0, lambda: messagebox.showerror("ngrok Error", 
                        "ngrok is not installed. Please install ngrok first:\n"
                        "1. Download from https://ngrok.com/download\n"
                        "2. Extract and add to PATH\n"
                        "3. Sign up and set auth token"))
                    return
                
                # Start ngrok
                self.ngrok_process = subprocess.Popen(
                    ['ngrok', 'http', str(self.port)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                time.sleep(3)  # Wait for ngrok to start
                
                # Get ngrok URL
                try:
                    response = requests.get('http://localhost:4040/api/tunnels')
                    data = response.json()
                    
                    if data['tunnels']:
                        public_url = data['tunnels'][0]['public_url']
                        self.root.after(0, lambda: self.ngrok_url.set(public_url))
                        self.root.after(0, lambda: self.ngrok_status.set("ngrok: Active"))
                        self.root.after(0, lambda: self.update_status(f"ngrok tunnel started: {public_url}"))
                    else:
                        raise Exception("No tunnels found")
                        
                except Exception as e:
                    self.root.after(0, lambda: self.update_status(f"Error getting ngrok URL: {str(e)}"))
                
            except Exception as e:
                self.root.after(0, lambda: self.update_status(f"Error starting ngrok: {str(e)}"))
                self.root.after(0, lambda: messagebox.showerror("ngrok Error", str(e)))
        
        threading.Thread(target=start_ngrok_thread, daemon=True).start()
    
    def stop_ngrok(self):
        """Stop ngrok tunnel"""
        if self.ngrok_process:
            self.ngrok_process.terminate()
            self.ngrok_process = None
            self.ngrok_url.set("")
            self.ngrok_status.set("ngrok: Not active")
            self.update_status("ngrok tunnel stopped")
    
    def add_files(self):
        """Add files to shared folder"""
        files = filedialog.askopenfilenames(title="Select files to share")
        if not files:
            return
        
        for file_path in files:
            try:
                filename = os.path.basename(file_path)
                dest_path = os.path.join(self.shared_folder, filename)
                shutil.copy2(file_path, dest_path)
                self.update_status(f"Added file: {filename}")
            except Exception as e:
                self.update_status(f"Error adding file {filename}: {str(e)}")
        
        self.refresh_file_list()
    
    def clear_files(self):
        """Clear all shared files"""
        try:
            for filename in os.listdir(self.shared_folder):
                file_path = os.path.join(self.shared_folder, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
            
            self.refresh_file_list()
            self.update_status("All files cleared")
        except Exception as e:
            self.update_status(f"Error clearing files: {str(e)}")
    
    def open_shared_folder(self):
        """Open the shared folder in file explorer"""
        try:
            if platform.system() == "Windows":
                os.startfile(self.shared_folder)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", self.shared_folder])
            else:  # Linux
                subprocess.run(["xdg-open", self.shared_folder])
        except Exception as e:
            self.update_status(f"Error opening folder: {str(e)}")
    
    def refresh_file_list(self):
        """Refresh the file list display"""
        # Clear existing items
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        
        # Add current files
        try:
            for filename in os.listdir(self.shared_folder):
                file_path = os.path.join(self.shared_folder, filename)
                if os.path.isfile(file_path):
                    size = os.path.getsize(file_path)
                    modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    # Format size
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024*1024:
                        size_str = f"{size/1024:.1f} KB"
                    else:
                        size_str = f"{size/(1024*1024):.1f} MB"
                    
                    self.file_tree.insert('', 'end', text=filename, 
                                        values=(size_str, modified.strftime("%Y-%m-%d %H:%M")))
        except Exception as e:
            self.update_status(f"Error refreshing file list: {str(e)}")
    
    def copy_url(self):
        """Copy local URL to clipboard"""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.server_url.get())
        self.update_status("Local URL copied to clipboard")
    
    def copy_ngrok_url(self):
        """Copy ngrok URL to clipboard"""
        if self.ngrok_url.get():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.ngrok_url.get())
            self.update_status("Public URL copied to clipboard")
    
    def open_url(self):
        """Open local URL in browser"""
        webbrowser.open(self.server_url.get())
    
    def open_ngrok_url(self):
        """Open ngrok URL in browser"""
        if self.ngrok_url.get():
            webbrowser.open(self.ngrok_url.get())
    
    def update_status(self, message):
        """Update status log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        self.status_text.insert(tk.END, log_message)
        self.status_text.see(tk.END)
        
        # Refresh file list periodically
        self.root.after(100, self.refresh_file_list)
    
    def on_closing(self):
        """Handle application closing"""
        if self.server:
            self.server.shutdown()
        
        if self.ngrok_process:
            self.ngrok_process.terminate()
        
        # Clean up temp folder
        try:
            shutil.rmtree(self.shared_folder)
        except:
            pass
        
        self.root.destroy()

def main():
    """Main function"""
    root = tk.Tk()
    app = FileTransferApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
