import os
import socket
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import json
import uuid

class LANChatServer:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.secret_key = str(uuid.uuid4())
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        
        # Configuration
        self.UPLOAD_FOLDER = 'shared_files'
        self.app.config['UPLOAD_FOLDER'] = self.UPLOAD_FOLDER
        self.app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
        
        # Data storage
        self.connected_users = {}
        self.chat_history = []
        self.server_stats = {
            'total_messages': 0,
            'total_files_shared': 0,
            'active_users': 0
        }
        
        # Create upload folder
        os.makedirs(self.UPLOAD_FOLDER, exist_ok=True)
        
        self.setup_routes()
        self.setup_socket_events()
        
    def get_local_ip(self):
        try:
            # Connect to a remote address to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def setup_routes(self):
        @self.app.route('/')
        def index():
            if 'username' not in session:
                return redirect(url_for('login'))
            return render_template('index.html', username=session['username'])
        
        @self.app.route('/login', methods=['GET', 'POST'])
        def login():
            if request.method == 'POST':
                username = request.form.get('username', '').strip()
                if username and len(username) <= 20:
                    session['username'] = username
                    return redirect(url_for('index'))
                else:
                    return render_template('login.html', error='Please enter a valid username (1-20 characters)')
            return render_template('login.html')
        
        @self.app.route('/logout')
        def logout():
            username = session.get('username')
            if username and username in self.connected_users:
                del self.connected_users[username]
                self.server_stats['active_users'] = len(self.connected_users)
            session.clear()
            return redirect(url_for('login'))
        
        @self.app.route('/upload', methods=['POST'])
        def upload_file():
            if 'file' not in request.files:
                return jsonify({'error': 'No file selected'})
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'})
            
            if file:
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + filename
                file_path = os.path.join(self.app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                self.server_stats['total_files_shared'] += 1
                
                # Notify all users about new file
                self.socketio.emit('file_uploaded', {
                    'filename': filename,
                    'original_name': file.filename,
                    'uploader': session.get('username', 'Anonymous'),
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                })
                
                return jsonify({'success': True, 'filename': filename})
        
        @self.app.route('/download/<filename>')
        def download_file(filename):
            try:
                return send_file(os.path.join(self.UPLOAD_FOLDER, filename), as_attachment=True)
            except:
                return "File not found", 404
        
        @self.app.route('/files')
        def list_files():
            try:
                files = []
                for filename in os.listdir(self.UPLOAD_FOLDER):
                    file_path = os.path.join(self.UPLOAD_FOLDER, filename)
                    if os.path.isfile(file_path):
                        file_stat = os.stat(file_path)
                        files.append({
                            'name': filename,
                            'size': file_stat.st_size,
                            'modified': datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                        })
                return jsonify(files)
            except:
                return jsonify([])
    
    def setup_socket_events(self):
        @self.socketio.on('connect')
        def handle_connect():
            username = session.get('username')
            if username:
                self.connected_users[username] = {
                    'sid': request.sid,
                    'joined': datetime.now().strftime('%H:%M:%S')
                }
                self.server_stats['active_users'] = len(self.connected_users)
                
                join_room('main_room')
                
                # Send chat history to new user
                emit('chat_history', self.chat_history)
                
                # Notify others
                emit('user_joined', {
                    'username': username,
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'total_users': len(self.connected_users)
                }, room='main_room')
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            username = session.get('username')
            if username and username in self.connected_users:
                del self.connected_users[username]
                self.server_stats['active_users'] = len(self.connected_users)
                
                emit('user_left', {
                    'username': username,
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'total_users': len(self.connected_users)
                }, room='main_room')
        
        @self.socketio.on('send_message')
        def handle_message(data):
            username = session.get('username')
            if username:
                message_data = {
                    'username': username,
                    'message': data['message'][:500],  # Limit message length
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'id': str(uuid.uuid4())
                }
                
                self.chat_history.append(message_data)
                if len(self.chat_history) > 100:  # Keep only last 100 messages
                    self.chat_history.pop(0)
                
                self.server_stats['total_messages'] += 1
                
                emit('new_message', message_data, room='main_room')
        
        @self.socketio.on('request_user_list')
        def handle_user_list():
            emit('user_list', {
                'users': list(self.connected_users.keys()),
                'total': len(self.connected_users)
            })
    
    def create_templates(self):
        # Create templates directory
        os.makedirs('templates', exist_ok=True)
        
        # Login page template
        login_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LAN Chat & File Share - Login</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            font-family: Tahoma, Arial, sans-serif;
            background: linear-gradient(45deg, #1e3c72, #2a5298);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .login-container {
            background: #f0f0f0;
            border: 3px outset #cccccc;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 5px 5px 15px rgba(0,0,0,0.3);
            width: 400px;
            text-align: center;
        }
        
        .login-container h1 {
            color: #2c5aa0;
            font-size: 24px;
            margin-bottom: 10px;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
        }
        
        .login-container h2 {
            color: #666;
            font-size: 16px;
            margin-bottom: 25px;
        }
        
        .form-group {
            margin-bottom: 20px;
            text-align: left;
        }
        
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #333;
        }
        
        input[type="text"] {
            width: 100%;
            padding: 8px;
            border: 2px inset #cccccc;
            border-radius: 3px;
            font-size: 14px;
            box-sizing: border-box;
        }
        
        .btn {
            background: linear-gradient(to bottom, #4CAF50, #45a049);
            border: 2px outset #4CAF50;
            color: white;
            padding: 10px 25px;
            font-size: 14px;
            font-weight: bold;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px;
        }
        
        .btn:hover {
            background: linear-gradient(to bottom, #45a049, #4CAF50);
            border: 2px inset #4CAF50;
        }
        
        .btn:active {
            border: 2px inset #cccccc;
        }
        
        .error {
            color: #d32f2f;
            background: #ffebee;
            border: 1px solid #e57373;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 15px;
        }
        
        .info-panel {
            background: #e3f2fd;
            border: 1px solid #90caf9;
            border-radius: 5px;
            padding: 15px;
            margin-top: 20px;
            text-align: left;
        }
        
        .info-panel h3 {
            margin-top: 0;
            color: #1976d2;
            font-size: 14px;
        }
        
        .info-panel ul {
            margin: 5px 0;
            padding-left: 20px;
            font-size: 12px;
            color: #555;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>LAN Chat & File Share</h1>
        <h2>Enter your name to join</h2>
        
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        
        <form method="POST">
            <div class="form-group">
                <label for="username">Your Name:</label>
                <input type="text" id="username" name="username" maxlength="20" required 
                       placeholder="Enter your name..." autocomplete="off">
            </div>
            <button type="submit" class="btn">Join Chat</button>
        </form>
        
        <div class="info-panel">
            <h3>Features Available:</h3>
            <ul>
                <li>Real-time group chat</li>
                <li>File sharing (up to 500MB)</li>
                <li>See who's online</li>
                <li>Download shared files</li>
            </ul>
        </div>
    </div>
</body>
</html>'''

        # Main application template
        main_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LAN Chat & File Share</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <style>
        body {
            margin: 0;
            padding: 0;
            font-family: Tahoma, Arial, sans-serif;
            background: linear-gradient(to bottom, #87CEEB, #98D4E8);
            min-height: 100vh;
        }
        
        .header {
            background: linear-gradient(to bottom, #2c5aa0, #1e3c72);
            color: white;
            padding: 10px 20px;
            border-bottom: 3px solid #1a252f;
            box-shadow: 0 2px 5px rgba(0,0,0,0.3);
        }
        
        .header h1 {
            margin: 0;
            font-size: 20px;
            display: inline-block;
        }
        
        .header-info {
            float: right;
            font-size: 12px;
            margin-top: 3px;
        }
        
        .main-container {
            display: flex;
            height: calc(100vh - 70px);
            gap: 10px;
            padding: 10px;
            box-sizing: border-box;
        }
        
        .chat-panel, .file-panel {
            background: #f0f0f0;
            border: 3px outset #cccccc;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            box-shadow: 3px 3px 8px rgba(0,0,0,0.2);
        }
        
        .chat-panel {
            flex: 2;
            min-width: 400px;
        }
        
        .file-panel {
            flex: 1;
            min-width: 300px;
        }
        
        .panel-header {
            background: linear-gradient(to bottom, #dcdcdc, #c0c0c0);
            border-bottom: 2px solid #999;
            padding: 8px 15px;
            font-weight: bold;
            color: #333;
            border-radius: 5px 5px 0 0;
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
            background: white;
            border: 2px inset #cccccc;
            margin: 5px;
            font-size: 13px;
        }
        
        .message {
            margin-bottom: 8px;
            padding: 5px 8px;
            border-radius: 3px;
            background: #f8f8f8;
            border-left: 3px solid #4CAF50;
        }
        
        .message.system {
            background: #fff3cd;
            border-left-color: #ffc107;
            font-style: italic;
            color: #856404;
        }
        
        .message-header {
            font-weight: bold;
            font-size: 11px;
            color: #666;
            margin-bottom: 2px;
        }
        
        .message-content {
            color: #333;
        }
        
        .chat-input {
            display: flex;
            padding: 10px;
            gap: 5px;
            background: #e0e0e0;
            border-top: 2px solid #999;
        }
        
        .chat-input input {
            flex: 1;
            padding: 8px;
            border: 2px inset #cccccc;
            border-radius: 3px;
            font-size: 13px;
        }
        
        .btn {
            background: linear-gradient(to bottom, #4CAF50, #45a049);
            border: 2px outset #4CAF50;
            color: white;
            padding: 8px 15px;
            font-size: 12px;
            font-weight: bold;
            border-radius: 3px;
            cursor: pointer;
        }
        
        .btn:hover {
            background: linear-gradient(to bottom, #45a049, #4CAF50);
        }
        
        .btn:active {
            border: 2px inset #cccccc;
        }
        
        .btn-secondary {
            background: linear-gradient(to bottom, #2196F3, #1976D2);
            border: 2px outset #2196F3;
        }
        
        .btn-secondary:hover {
            background: linear-gradient(to bottom, #1976D2, #2196F3);
        }
        
        .btn-danger {
            background: linear-gradient(to bottom, #f44336, #d32f2f);
            border: 2px outset #f44336;
        }
        
        .btn-danger:hover {
            background: linear-gradient(to bottom, #d32f2f, #f44336);
        }
        
        .file-upload {
            padding: 15px;
            border-bottom: 1px solid #ccc;
        }
        
        .file-input {
            margin-bottom: 10px;
        }
        
        .file-input input[type="file"] {
            width: 100%;
            padding: 5px;
            border: 2px inset #cccccc;
            background: white;
            font-size: 12px;
        }
        
        .file-list {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
            background: white;
            border: 2px inset #cccccc;
            margin: 5px;
        }
        
        .file-item {
            background: #f8f8f8;
            border: 1px solid #ddd;
            border-radius: 3px;
            padding: 8px;
            margin-bottom: 5px;
            font-size: 12px;
        }
        
        .file-item:hover {
            background: #e8e8e8;
        }
        
        .file-name {
            font-weight: bold;
            color: #333;
            margin-bottom: 3px;
            word-break: break-word;
        }
        
        .file-info {
            color: #666;
            font-size: 11px;
        }
        
        .online-users {
            background: #e8f4fd;
            border: 1px solid #90caf9;
            border-radius: 5px;
            padding: 10px;
            margin: 10px;
            font-size: 12px;
        }
        
        .online-users h4 {
            margin: 0 0 8px 0;
            color: #1976d2;
            font-size: 13px;
        }
        
        .user-list {
            color: #555;
        }
        
        .status-bar {
            background: #f0f0f0;
            border-top: 1px solid #ccc;
            padding: 5px 10px;
            font-size: 11px;
            color: #666;
            text-align: center;
        }
        
        .upload-progress {
            display: none;
            background: #fff3cd;
            border: 1px solid #ffc107;
            padding: 8px;
            margin: 5px 0;
            border-radius: 3px;
            font-size: 12px;
            color: #856404;
        }
        
        @media (max-width: 768px) {
            .main-container {
                flex-direction: column;
                height: auto;
            }
            
            .chat-panel, .file-panel {
                min-width: auto;
                height: 300px;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>LAN Chat & File Share</h1>
        <div class="header-info">
            Welcome, <strong>{{ username }}</strong> | 
            <a href="/logout" style="color: #87CEEB;">Logout</a>
        </div>
        <div style="clear: both;"></div>
    </div>
    
    <div class="main-container">
        <div class="chat-panel">
            <div class="panel-header">Chat Room</div>
            <div class="chat-messages" id="chatMessages"></div>
            <div class="chat-input">
                <input type="text" id="messageInput" placeholder="Type your message..." maxlength="500">
                <button class="btn" onclick="sendMessage()">Send</button>
            </div>
        </div>
        
        <div class="file-panel">
            <div class="panel-header">File Sharing</div>
            
            <div class="file-upload">
                <div class="file-input">
                    <input type="file" id="fileInput" multiple>
                </div>
                <button class="btn btn-secondary" onclick="uploadFile()">Upload Files</button>
                <div class="upload-progress" id="uploadProgress">Uploading...</div>
            </div>
            
            <div class="online-users">
                <h4>Online Users (<span id="userCount">0</span>)</h4>
                <div class="user-list" id="userList">Loading...</div>
            </div>
            
            <div class="file-list" id="fileList">Loading files...</div>
        </div>
    </div>
    
    <div class="status-bar">
        <span id="connectionStatus">Connecting...</span>
    </div>
    
    <script>
        const socket = io();
        let username = "{{ username }}";
        
        // Socket event handlers
        socket.on('connect', function() {
            document.getElementById('connectionStatus').textContent = 'Connected to server';
            socket.emit('request_user_list');
            loadFiles();
        });
        
        socket.on('disconnect', function() {
            document.getElementById('connectionStatus').textContent = 'Disconnected from server';
        });
        
        socket.on('chat_history', function(history) {
            const messagesDiv = document.getElementById('chatMessages');
            messagesDiv.innerHTML = '';
            history.forEach(msg => addMessage(msg));
        });
        
        socket.on('new_message', function(data) {
            addMessage(data);
        });
        
        socket.on('user_joined', function(data) {
            addSystemMessage(data.username + " joined the chat", data.timestamp);
            updateUserCount(data.total_users);
            socket.emit('request_user_list');
        });
        
        socket.on('user_left', function(data) {
            addSystemMessage(data.username + " left the chat", data.timestamp);
            updateUserCount(data.total_users);
            socket.emit('request_user_list');
        });
        
        socket.on('user_list', function(data) {
            updateUserList(data.users);
            updateUserCount(data.total);
        });
        
        socket.on('file_uploaded', function(data) {
            addSystemMessage(data.uploader + " shared a file: " + data.original_name, data.timestamp);
            loadFiles();
        });
        
        // Chat functions
        function addMessage(data) {
            const messagesDiv = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message';
            
            messageDiv.innerHTML = `
                <div class="message-header">${data.username} - ${data.timestamp}</div>
                <div class="message-content">${escapeHtml(data.message)}</div>
            `;
            
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        function addSystemMessage(message, timestamp) {
            const messagesDiv = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message system';
            
            messageDiv.innerHTML = `
                <div class="message-header">System - ${timestamp}</div>
                <div class="message-content">${message}</div>
            `;
            
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        function sendMessage() {
            const input = document.getElementById('messageInput');
            const message = input.value.trim();
            
            if (message) {
                socket.emit('send_message', { message: message });
                input.value = '';
            }
        }
        
        // File functions
        function uploadFile() {
            const fileInput = document.getElementById('fileInput');
            const files = fileInput.files;
            
            if (files.length === 0) {
                alert('Please select files to upload');
                return;
            }
            
            const progress = document.getElementById('uploadProgress');
            progress.style.display = 'block';
            
            // Upload files one by one
            uploadNextFile(files, 0, progress);
        }
        
        function uploadNextFile(files, index, progressDiv) {
            if (index >= files.length) {
                progressDiv.style.display = 'none';
                document.getElementById('fileInput').value = '';
                return;
            }
            
            const file = files[index];
            const formData = new FormData();
            formData.append('file', file);
            
            progressDiv.textContent = `Uploading ${file.name} (${index + 1}/${files.length})...`;
            
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    alert('Upload failed: ' + data.error);
                }
                uploadNextFile(files, index + 1, progressDiv);
            })
            .catch(error => {
                alert('Upload failed: ' + error);
                uploadNextFile(files, index + 1, progressDiv);
            });
        }
        
        function loadFiles() {
            fetch('/files')
            .then(response => response.json())
            .then(files => {
                const fileList = document.getElementById('fileList');
                if (files.length === 0) {
                    fileList.innerHTML = '<div style="text-align: center; color: #666; padding: 20px;">No files shared yet</div>';
                    return;
                }
                
                fileList.innerHTML = '';
                files.forEach(file => {
                    const fileDiv = document.createElement('div');
                    fileDiv.className = 'file-item';
                    
                    const displayName = file.name.substring(16); // Remove timestamp prefix
                    const fileSize = formatFileSize(file.size);
                    
                    fileDiv.innerHTML = `
                        <div class="file-name">${escapeHtml(displayName)}</div>
                        <div class="file-info">Size: ${fileSize} | Modified: ${file.modified}</div>
                        <button class="btn btn-secondary" style="margin-top: 5px; font-size: 11px;" 
                                onclick="downloadFile('${file.name}')">Download</button>
                    `;
                    
                    fileList.appendChild(fileDiv);
                });
            });
        }
        
        function downloadFile(filename) {
            window.open('/download/' + encodeURIComponent(filename), '_blank');
        }
        
        function updateUserList(users) {
            const userList = document.getElementById('userList');
            if (users.length === 0) {
                userList.textContent = 'No users online';
            } else {
                userList.textContent = users.join(', ');
            }
        }
        
        function updateUserCount(count) {
            document.getElementById('userCount').textContent = count;
        }
        
        // Utility functions
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        // Event listeners
        document.getElementById('messageInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
        
        // Load files on page load
        document.addEventListener('DOMContentLoaded', function() {
            loadFiles();
        });
    </script>
</body>
</html>'''
        
        # Write templates
        with open('templates/login.html', 'w', encoding='utf-8') as f:
            f.write(login_html)
        
        with open('templates/index.html', 'w', encoding='utf-8') as f:
            f.write(main_html)
    
    def run_gui(self):
        def start_server():
            try:
                host = self.get_local_ip()
                port = int(port_var.get())
                
                # Update server info
                server_url = f"http://{host}:{port}"
                url_label.config(text=f"Server URL: {server_url}")
                
                # Start server in separate thread
                server_thread = threading.Thread(
                    target=lambda: self.socketio.run(self.app, host='0.0.0.0', port=port, debug=False),
                    daemon=True
                )
                server_thread.start()
                
                start_btn.config(state='disabled')
                stop_btn.config(state='normal')
                status_label.config(text="Server Status: Running", fg="green")
                
                # Start stats update
                update_stats()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to start server: {str(e)}")
        
        def stop_server():
            try:
                start_btn.config(state='normal')
                stop_btn.config(state='disabled')
                status_label.config(text="Server Status: Stopped", fg="red")
                url_label.config(text="Server URL: Not running")
                messagebox.showinfo("Server", "Server stopped. Note: You may need to restart the application to start the server again.")
            except Exception as e:
                messagebox.showerror("Error", f"Error stopping server: {str(e)}")
        
        def update_stats():
            if status_label.cget("text") == "Server Status: Running":
                # Update statistics
                stats_text.delete(1.0, tk.END)
                stats_content = f"""=== SERVER STATISTICS ===
Active Users: {self.server_stats['active_users']}
Total Messages Sent: {self.server_stats['total_messages']}
Files Shared: {self.server_stats['total_files_shared']}
Server Uptime: {datetime.now().strftime('%H:%M:%S')}

=== CONNECTED USERS ===
"""
                if self.connected_users:
                    for username, info in self.connected_users.items():
                        stats_content += f"• {username} (joined: {info['joined']})\n"
                else:
                    stats_content += "No users connected\n"
                
                stats_content += f"\n=== RECENT CHAT ACTIVITY ===\n"
                if self.chat_history:
                    for msg in self.chat_history[-5:]:  # Last 5 messages
                        stats_content += f"[{msg['timestamp']}] {msg['username']}: {msg['message'][:50]}{'...' if len(msg['message']) > 50 else ''}\n"
                else:
                    stats_content += "No recent messages\n"
                
                stats_text.insert(tk.END, stats_content)
                
                # Schedule next update
                root.after(2000, update_stats)
        
        def select_upload_folder():
            folder = filedialog.askdirectory(title="Select Upload Folder")
            if folder:
                self.UPLOAD_FOLDER = folder
                self.app.config['UPLOAD_FOLDER'] = folder
                upload_folder_label.config(text=f"Upload Folder: {folder}")
        
        def clear_chat_history():
            if messagebox.askyesno("Clear Chat", "Are you sure you want to clear all chat history?"):
                self.chat_history.clear()
                self.server_stats['total_messages'] = 0
                messagebox.showinfo("Chat Cleared", "Chat history has been cleared.")
        
        def clear_files():
            if messagebox.askyesno("Clear Files", "Are you sure you want to delete all shared files?"):
                try:
                    for filename in os.listdir(self.UPLOAD_FOLDER):
                        file_path = os.path.join(self.UPLOAD_FOLDER, filename)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    self.server_stats['total_files_shared'] = 0
                    messagebox.showinfo("Files Cleared", "All shared files have been deleted.")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to clear files: {str(e)}")
        
        # Create main window
        root = tk.Tk()
        root.title("LAN Chat & File Share Server Control")
        root.geometry("800x600")
        root.configure(bg="#f0f0f0")
        
        # Variables
        port_var = tk.StringVar(value="5000")
        
        # Main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Server Control Section
        control_frame = ttk.LabelFrame(main_frame, text="Server Control", padding="10")
        control_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(control_frame, text="Port:").grid(row=0, column=0, sticky=tk.W)
        port_entry = ttk.Entry(control_frame, textvariable=port_var, width=10)
        port_entry.grid(row=0, column=1, padx=(5, 10))
        
        start_btn = ttk.Button(control_frame, text="Start Server", command=start_server)
        start_btn.grid(row=0, column=2, padx=5)
        
        stop_btn = ttk.Button(control_frame, text="Stop Server", command=stop_server, state='disabled')
        stop_btn.grid(row=0, column=3, padx=5)
        
        status_label = ttk.Label(control_frame, text="Server Status: Stopped", foreground="red")
        status_label.grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(10, 0))
        
        url_label = ttk.Label(control_frame, text="Server URL: Not running", foreground="blue")
        url_label.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(5, 0))
        
        # Configuration Section
        config_frame = ttk.LabelFrame(main_frame, text="Configuration", padding="10")
        config_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        upload_folder_label = ttk.Label(config_frame, text=f"Upload Folder: {self.UPLOAD_FOLDER}")
        upload_folder_label.grid(row=0, column=0, sticky=tk.W)
        
        ttk.Button(config_frame, text="Change Folder", command=select_upload_folder).grid(row=0, column=1, padx=(10, 0))
        
        # Management Section
        mgmt_frame = ttk.LabelFrame(main_frame, text="Management", padding="10")
        mgmt_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Button(mgmt_frame, text="Clear Chat History", command=clear_chat_history).grid(row=0, column=0, padx=(0, 10))
        ttk.Button(mgmt_frame, text="Clear All Files", command=clear_files).grid(row=0, column=1)
        
        # Statistics Section
        stats_frame = ttk.LabelFrame(main_frame, text="Server Statistics & Activity", padding="10")
        stats_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        stats_text = scrolledtext.ScrolledText(stats_frame, width=80, height=20, font=("Courier", 9))
        stats_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        control_frame.columnconfigure(4, weight=1)
        config_frame.columnconfigure(2, weight=1)
        mgmt_frame.columnconfigure(2, weight=1)
        stats_frame.columnconfigure(0, weight=1)
        stats_frame.rowconfigure(0, weight=1)
        
        # Initial stats display
        stats_text.insert(tk.END, "=== LAN CHAT & FILE SHARE SERVER ===\n\n")
        stats_text.insert(tk.END, "Welcome to the LAN Chat & File Share Server!\n\n")
        stats_text.insert(tk.END, "Features:\n")
        stats_text.insert(tk.END, "• Real-time group chat\n")
        stats_text.insert(tk.END, "• File sharing up to 500MB per file\n")
        stats_text.insert(tk.END, "• Multiple file upload support\n")
        stats_text.insert(tk.END, "• User presence indicators\n")
        stats_text.insert(tk.END, "• Responsive 2000s-style web interface\n")
        stats_text.insert(tk.END, "• Cross-platform compatibility\n\n")
        stats_text.insert(tk.END, "Instructions:\n")
        stats_text.insert(tk.END, "1. Click 'Start Server' to begin\n")
        stats_text.insert(tk.END, "2. Share the Server URL with your friends\n")
        stats_text.insert(tk.END, "3. Everyone can chat and share files!\n\n")
        stats_text.insert(tk.END, "Server ready to start...\n")
        
        return root

def main():
    # Create server instance
    server = LANChatServer()
    
    # Create templates
    server.create_templates()
    
    print("=" * 60)
    print("LAN CHAT & FILE SHARE SERVER")
    print("=" * 60)
    print("Setting up server...")
    print("Creating web templates...")
    print("Initializing chat system...")
    print("Ready to start!")
    print("=" * 60)
    
    # Run GUI
    root = server.run_gui()
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nShutting down server...")

if __name__ == "__main__":
    main()
