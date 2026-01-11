#!/usr/bin/env python3
"""
MacHPCClusterJobScheduler.py

Enhanced HPC Dashboard for macOS with OpenMPI:
- SSH agent & GUI passphrase for encrypted private keys
- Submit Python/MATLAB scripts to OpenMPI cluster
- Job history (SQLite: ~/Documents/.MacHPCClusterJobScheduler.db) and job-watcher
- Shared-folder helpers (NFS guidance + SFTP fallback sync)
- Multi-GPU Metal support
- Cluster node monitoring

Dependencies:
    pip install pyqt5 paramiko matplotlib
Run:
    python3 MacHPCClusterJobScheduler.py
"""
from __future__ import annotations
import sys, os, json, time, re, sqlite3
from datetime import datetime
from pathlib import Path
import threading
import subprocess

import paramiko
from paramiko.agent import Agent
from paramiko.ssh_exception import PasswordRequiredException
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QTextEdit,
    QHBoxLayout, QVBoxLayout, QFileDialog, QMessageBox, QPlainTextEdit,
    QInputDialog, QCheckBox, QSpinBox, QComboBox, QTableWidget, QTableWidgetItem
)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# ---------------- constants ----------------
POLL_INTERVAL = 8.0
JOB_WATCH_INTERVAL = 10.0
DB_PATH = Path.home() / 'Documents' / '.MacHPCClusterJobScheduler.db'
CONFIG_PATH = Path.home() / 'Documents' / '.MacHPCClusterJobScheduler_conf.json'
LOCAL_JOB_OUTPUT_DIR = Path.home() / 'Documents' / 'MacHPCClusterJobScheduler_Outputs'
HOSTS_FILE = 'hosts.txt'

# Create output directory
LOCAL_JOB_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------- DB helpers ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jobid TEXT,
            job_name TEXT,
            remote_script TEXT,
            remote_out TEXT,
            remote_err TEXT,
            submitted_at TEXT,
            status TEXT,
            command TEXT,
            num_procs INTEGER,
            nodes TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS cluster_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            node TEXT,
            cpu_percent REAL,
            mem_percent REAL,
            load_avg REAL
        )
    ''')
    conn.commit()
    conn.close()

def insert_job_record(jobid, job_name, remote_script, remote_out, remote_err, command, num_procs, nodes, status='RUNNING'):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO jobs (jobid, job_name, remote_script, remote_out, remote_err, 
                 submitted_at, status, command, num_procs, nodes) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (str(jobid), job_name, remote_script, remote_out, remote_err,
               datetime.utcnow().isoformat(), status, command, num_procs, nodes))
    conn.commit()
    conn.close()

def update_job_status(jobid, new_status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE jobs SET status=? WHERE jobid=?', (new_status, str(jobid)))
    conn.commit()
    conn.close()

def list_jobs(limit=100):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT jobid, job_name, remote_script, remote_out, submitted_at, status, num_procs, nodes 
                 FROM jobs ORDER BY id DESC LIMIT ?''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def insert_cluster_stats(ts, node, cpu_percent, mem_percent, load_avg):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO cluster_history (ts, node, cpu_percent, mem_percent, load_avg) VALUES (?, ?, ?, ?, ?)',
              (ts.isoformat(), node, cpu_percent, mem_percent, load_avg))
    conn.commit()
    conn.close()

# ---------- config ----------
def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except:
            return {}
    return {}

def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except:
        pass

# ---------- SSH helper ----------
class SSHClientEnhanced:
    def __init__(self, hostname, username, key_path=None, password=None, port=22, passphrase_callback=None):
        self.hostname = hostname
        self.username = username
        self.key_path = key_path
        self.password = password
        self.port = port
        self.passphrase_callback = passphrase_callback
        self.client = None
        self.sftp = None

    def _load_private_key(self, path):
        last_exc = None
        for KeyClass in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey):
            try:
                return KeyClass.from_private_key_file(path)
            except PasswordRequiredException as e:
                last_exc = e
                if self.passphrase_callback:
                    pw = self.passphrase_callback()
                    if pw is None:
                        raise RuntimeError('Passphrase canceled')
                    try:
                        return KeyClass.from_private_key_file(path, password=pw)
                    except Exception as e2:
                        last_exc = e2
                        continue
                else:
                    raise
            except Exception as e:
                last_exc = e
                continue
        if last_exc:
            raise last_exc
        return None

    def connect(self, timeout=12):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = None
        if self.key_path:
            pkey = self._load_private_key(self.key_path)
        try:
            if pkey:
                self.client.connect(self.hostname, port=self.port, username=self.username,
                                  pkey=pkey, timeout=timeout)
            elif self.password:
                self.client.connect(self.hostname, port=self.port, username=self.username,
                                  password=self.password, timeout=timeout)
            else:
                try:
                    agent = Agent()
                    keys = agent.get_keys()
                    if keys:
                        connected = False
                        last_exc = None
                        for k in keys:
                            try:
                                self.client.connect(self.hostname, port=self.port,
                                                  username=self.username, pkey=k, timeout=timeout)
                                connected = True
                                break
                            except Exception as e:
                                last_exc = e
                        if not connected:
                            self.client.connect(self.hostname, port=self.port,
                                              username=self.username, timeout=timeout)
                    else:
                        self.client.connect(self.hostname, port=self.port,
                                          username=self.username, timeout=timeout)
                except Exception:
                    self.client.connect(self.hostname, port=self.port,
                                      username=self.username, timeout=timeout)
            self.sftp = self.client.open_sftp()
        except Exception as e:
            raise RuntimeError(f"SSH connect failed: {e}")

    def exec(self, cmd, timeout=20):
        if self.client is None:
            raise RuntimeError("Not connected")
        stdin, stdout, stderr = self.client.exec_command(cmd, timeout=timeout)
        return (stdout.read().decode('utf-8', errors='ignore').strip(),
                stderr.read().decode('utf-8', errors='ignore').strip())

    def put(self, local_path, remote_path):
        if self.sftp is None:
            raise RuntimeError("SFTP not connected")
        self.sftp.put(local_path, remote_path)

    def get(self, remote_path, local_path):
        if self.sftp is None:
            raise RuntimeError("SFTP not connected")
        self.sftp.get(remote_path, local_path)

    def listdir(self, remote_path):
        if self.sftp is None:
            raise RuntimeError("SFTP not connected")
        try:
            return self.sftp.listdir(remote_path)
        except Exception:
            return []

    def mkdir(self, remote_path):
        if self.sftp is None:
            raise RuntimeError("SFTP not connected")
        try:
            self.sftp.mkdir(remote_path)
        except Exception:
            pass

    def close(self):
        try:
            if self.sftp:
                self.sftp.close()
        except:
            pass
        try:
            if self.client:
                self.client.close()
        except:
            pass
        self.client = None
        self.sftp = None

# ---------- plotting ----------
class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=8, height=3, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.ax = fig.add_subplot(111)
        super().__init__(fig)
        fig.tight_layout(pad=2.0)

# ---------- main GUI ----------
class HPCDashboard(QWidget):
    def __init__(self):
        super().__init__()
        init_db()
        self.cfg = load_config()
        self.ssh = None
        self.polling = False
        self.poll_thread = None
        self.job_watcher_thread = None
        self.cluster_nodes = []
        self.node_stats = {}
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("macOS HPC Cluster - OpenMPI Dashboard")
        self.resize(1200, 850)

        # Connection row
        self.host_edit = QLineEdit(self.cfg.get('host', ''))
        self.user_edit = QLineEdit(self.cfg.get('user', ''))
        self.key_edit = QLineEdit(self.cfg.get('key_path', ''))
        btn_browse_key = QPushButton("Browse")
        btn_browse_key.clicked.connect(self.browse_key)
        btn_connect = QPushButton("Connect")
        btn_connect.clicked.connect(self.connect_clicked)
        btn_disconnect = QPushButton("Disconnect")
        btn_disconnect.clicked.connect(self.disconnect_clicked)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Controller:"))
        row1.addWidget(self.host_edit)
        row1.addWidget(QLabel("User:"))
        row1.addWidget(self.user_edit)
        row1.addWidget(QLabel("SSH Key:"))
        row1.addWidget(self.key_edit)
        row1.addWidget(btn_browse_key)
        row1.addWidget(btn_connect)
        row1.addWidget(btn_disconnect)

        # Quick actions
        btn_nodes = QPushButton("List Nodes")
        btn_nodes.clicked.connect(self.list_cluster_nodes)
        btn_gpus = QPushButton("Detect GPUs")
        btn_gpus.clicked.connect(self.detect_cluster_gpus)
        btn_refresh = QPushButton("Refresh Status")
        btn_refresh.clicked.connect(self.poll_once)
        btn_history = QPushButton("Job History")
        btn_history.clicked.connect(self.show_job_history)
        
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_nodes)
        btn_row.addWidget(btn_gpus)
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_history)

        # Cluster nodes table
        self.nodes_table = QTableWidget()
        self.nodes_table.setColumnCount(5)
        self.nodes_table.setHorizontalHeaderLabels(["Node", "Status", "CPUs", "Memory", "GPUs"])
        self.nodes_table.setMaximumHeight(120)

        # Hosts file configuration
        self.hosts_file_path = QLineEdit(self.cfg.get('hosts_file', 'hosts.txt'))
        btn_browse_hosts = QPushButton("Browse")
        btn_browse_hosts.clicked.connect(self.browse_hosts_file)
        btn_edit_hosts = QPushButton("Edit Hosts File")
        btn_edit_hosts.clicked.connect(self.edit_hosts_file)
        
        hosts_row = QHBoxLayout()
        hosts_row.addWidget(QLabel("Hosts File:"))
        hosts_row.addWidget(self.hosts_file_path)
        hosts_row.addWidget(btn_browse_hosts)
        hosts_row.addWidget(btn_edit_hosts)

        # Shared folder controls
        self.shared_path_edit = QLineEdit(self.cfg.get('shared_path', '/srv/hpc/shared'))
        btn_ensure_shared = QPushButton("Create Shared Folder")
        btn_ensure_shared.clicked.connect(self.ensure_shared_folder)
        btn_fetch_shared = QPushButton("Fetch Results")
        btn_fetch_shared.clicked.connect(self.fetch_shared_results)
        
        shared_row = QHBoxLayout()
        shared_row.addWidget(QLabel("Shared Path:"))
        shared_row.addWidget(self.shared_path_edit)
        shared_row.addWidget(btn_ensure_shared)
        shared_row.addWidget(btn_fetch_shared)

        # Job submission controls
        self.remote_base_path = QLineEdit(self.cfg.get('remote_base_path', f"/home/{os.getlogin()}"))
        self.script_path = QLineEdit()
        self.script_type = QComboBox()
        self.script_type.addItems(["Python", "MATLAB", "Shell Script"])
        btn_browse_script = QPushButton("Browse Script")
        btn_browse_script.clicked.connect(self.browse_script)
        
        self.use_gpu = QCheckBox("Use GPU")
        self.num_procs = QSpinBox()
        self.num_procs.setRange(1, 256)
        self.num_procs.setValue(4)
        self.script_args = QLineEdit()
        btn_submit = QPushButton("Submit Job")
        btn_submit.clicked.connect(self.submit_mpi_job)

        job_row1 = QHBoxLayout()
        job_row1.addWidget(QLabel("Remote Base:"))
        job_row1.addWidget(self.remote_base_path)
        job_row1.addWidget(QLabel("Script:"))
        job_row1.addWidget(self.script_path)
        job_row1.addWidget(btn_browse_script)
        
        job_row2 = QHBoxLayout()
        job_row2.addWidget(QLabel("Type:"))
        job_row2.addWidget(self.script_type)
        job_row2.addWidget(self.use_gpu)
        job_row2.addWidget(QLabel("# Processes:"))
        job_row2.addWidget(self.num_procs)
        job_row2.addWidget(QLabel("Args:"))
        job_row2.addWidget(self.script_args)
        job_row2.addWidget(btn_submit)

        # Chart for cluster monitoring
        self.canvas = MplCanvas(self, width=10, height=3.5)
        self.canvas.ax.set_title("Cluster CPU Usage")
        self.canvas.ax.set_xlabel("Time")
        self.canvas.ax.set_ylabel("CPU %")

        # Advanced MPI command editor
        self.mpi_cmd_editor = QTextEdit()
        self.mpi_cmd_editor.setPlainText("# Advanced MPI command editor\n# Example:\nmpirun --hostfile hosts.txt -np 8 python script.py")
        self.mpi_cmd_editor.setMaximumHeight(100)
        btn_run_custom = QPushButton("Run Custom MPI Command")
        btn_run_custom.clicked.connect(self.run_custom_mpi_command)

        # Log
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(200)

        # Assemble layout
        layout = QVBoxLayout()
        layout.addLayout(row1)
        layout.addLayout(btn_row)
        layout.addWidget(QLabel("Cluster Nodes:"))
        layout.addWidget(self.nodes_table)
        layout.addLayout(hosts_row)
        layout.addLayout(shared_row)
        layout.addWidget(QLabel("Job Submission:"))
        layout.addLayout(job_row1)
        layout.addLayout(job_row2)
        layout.addWidget(self.canvas)
        layout.addWidget(QLabel("Advanced MPI Command:"))
        layout.addWidget(self.mpi_cmd_editor)
        layout.addWidget(btn_run_custom)
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self.log)
        self.setLayout(layout)

    # ---------- UI helpers ----------
    def browse_key(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select SSH private key", str(Path.home()))
        if p:
            self.key_edit.setText(p)

    def browse_hosts_file(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select hosts file", str(Path.cwd()), "Text Files (*.txt)")
        if p:
            self.hosts_file_path.setText(p)

    def browse_script(self):
        script_type = self.script_type.currentText()
        if script_type == "Python":
            filter_str = "Python Files (*.py)"
        elif script_type == "MATLAB":
            filter_str = "MATLAB Files (*.m)"
        else:
            filter_str = "Shell Scripts (*.sh)"
        
        p, _ = QFileDialog.getOpenFileName(self, "Select script", str(Path.home()), filter_str)
        if p:
            self.script_path.setText(p)

    def append_log(self, text):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log.appendPlainText(f"[{ts}] {text}")

    def _ask_passphrase(self):
        pw, ok = QInputDialog.getText(self, 'SSH passphrase',
                                     'Enter passphrase for SSH key:',
                                     QLineEdit.Password)
        return pw if ok else None

    # ---------- connection ----------
    def connect_clicked(self):
        host = self.host_edit.text().strip()
        user = self.user_edit.text().strip()
        key = self.key_edit.text().strip() or None
        
        if not host or not user:
            QMessageBox.warning(self, "Missing Info", "Enter host and username")
            return
        
        self.append_log(f"Connecting to {user}@{host}...")
        try:
            self.ssh = SSHClientEnhanced(host, user, key_path=key,
                                        passphrase_callback=self._ask_passphrase)
            self.ssh.connect()
        except Exception as e:
            self.append_log(f"Connection failed: {e}")
            QMessageBox.critical(self, "SSH Error", str(e))
            self.ssh = None
            return
        
        self.append_log("✅ Connected successfully")
        self.cfg['host'] = host
        self.cfg['user'] = user
        self.cfg['key_path'] = key
        save_config(self.cfg)
        
        # Start monitoring threads
        if not self.polling:
            self.polling = True
            self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
            self.poll_thread.start()
        
        if not self.job_watcher_thread:
            self.job_watcher_thread = threading.Thread(target=self._job_watcher_loop, daemon=True)
            self.job_watcher_thread.start()
        
        # Initial checks
        self.list_cluster_nodes()
        self.detect_cluster_gpus()

    def disconnect_clicked(self):
        self.append_log("Disconnecting...")
        self.polling = False
        if self.ssh:
            try:
                self.ssh.close()
            except:
                pass
        self.ssh = None
        self.append_log("Disconnected")

    # ---------- cluster management ----------
    def list_cluster_nodes(self):
        """Parse hosts file and check node availability"""
        if not self.ssh:
            QMessageBox.warning(self, "Not connected", "Connect first")
            return
        
        hosts_file = self.hosts_file_path.text().strip()
        if not hosts_file or not Path(hosts_file).exists():
            self.append_log("⚠️  Hosts file not found")
            return
        
        self.cluster_nodes = []
        self.nodes_table.setRowCount(0)
        
        try:
            with open(hosts_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split()
                    if len(parts) >= 1:
                        hostname = parts[0]
                        slots = 1
                        for part in parts[1:]:
                            if 'slots=' in part:
                                slots = int(part.split('=')[1])
                        self.cluster_nodes.append({'hostname': hostname, 'slots': slots})
        except Exception as e:
            self.append_log(f"Error reading hosts file: {e}")
            return
        
        # Check each node
        for node in self.cluster_nodes:
            hostname = node['hostname']
            row = self.nodes_table.rowCount()
            self.nodes_table.insertRow(row)
            self.nodes_table.setItem(row, 0, QTableWidgetItem(hostname))
            
            try:
                # Check if node is reachable
                out, err = self.ssh.exec(f"ssh -o ConnectTimeout=3 {hostname} 'echo OK'", timeout=5)
                if 'OK' in out:
                    self.nodes_table.setItem(row, 1, QTableWidgetItem("✅ Online"))
                    
                    # Get CPU count
                    out, _ = self.ssh.exec(f"ssh {hostname} 'sysctl -n hw.ncpu'", timeout=5)
                    cpus = out.strip() if out else str(node['slots'])
                    self.nodes_table.setItem(row, 2, QTableWidgetItem(cpus))
                    
                    # Get memory
                    out, _ = self.ssh.exec(f"ssh {hostname} 'sysctl -n hw.memsize'", timeout=5)
                    if out:
                        mem_gb = int(out.strip()) / (1024**3)
                        self.nodes_table.setItem(row, 3, QTableWidgetItem(f"{mem_gb:.1f} GB"))
                else:
                    self.nodes_table.setItem(row, 1, QTableWidgetItem("❌ Offline"))
            except Exception as e:
                self.nodes_table.setItem(row, 1, QTableWidgetItem("❌ Offline"))
                self.append_log(f"Node {hostname} check failed: {e}")
        
        self.append_log(f"Found {len(self.cluster_nodes)} nodes in cluster")

    def detect_cluster_gpus(self):
        """Detect Metal GPUs on all cluster nodes"""
        if not self.ssh:
            return
        
        for idx, node in enumerate(self.cluster_nodes):
            hostname = node['hostname']
            try:
                # Try to detect Metal GPUs using python
                cmd = f"ssh {hostname} 'python3 -c \"import Metal; print(len(Metal.MTLCopyAllDevices()))\"'"
                out, err = self.ssh.exec(cmd, timeout=5)
                if out and out.isdigit():
                    gpu_count = int(out)
                    self.nodes_table.setItem(idx, 4, QTableWidgetItem(f"{gpu_count} GPU(s)"))
                    node['gpus'] = gpu_count
                else:
                    self.nodes_table.setItem(idx, 4, QTableWidgetItem("N/A"))
            except Exception as e:
                self.nodes_table.setItem(idx, 4, QTableWidgetItem("N/A"))

    def edit_hosts_file(self):
        """Open hosts file in external editor"""
        hosts_file = self.hosts_file_path.text().strip()
        if not hosts_file:
            QMessageBox.warning(self, "No file", "Specify hosts file path")
            return
        
        if not Path(hosts_file).exists():
            # Create template
            template = "# MPI Hosts Configuration\n# Format: hostname slots=N\n\nmac-studio.local slots=8\nmac-pro.local slots=12\n"
            Path(hosts_file).write_text(template)
        
        # Open with default editor
        if sys.platform == 'darwin':
            subprocess.Popen(['open', '-t', hosts_file])
        else:
            subprocess.Popen(['xdg-open', hosts_file])
        
        self.append_log(f"Opened {hosts_file} in editor")

    # ---------- shared folder ----------
    def ensure_shared_folder(self):
        """Create remote shared path and subfolders"""
        if not self.ssh:
            QMessageBox.warning(self, "Not connected", "Connect first")
            return
        
        remote = self.shared_path_edit.text().strip()
        if not remote:
            QMessageBox.warning(self, "Missing", "Enter shared remote path")
            return
        
        try:
            self.append_log(f"Creating remote folder {remote}...")
            self.ssh.exec(f"mkdir -p {remote} && chmod 2775 {remote} || true")
            for d in ('inputs', 'outputs', 'tmp', 'logs'):
                self.ssh.mkdir(f"{remote}/{d}")
            self.append_log("✅ Shared path created (use NFS for true shared filesystem)")
            self.cfg['shared_path'] = remote
            save_config(self.cfg)
        except Exception as e:
            self.append_log(f"Error creating shared folder: {e}")

    def fetch_shared_results(self):
        """Download all files from remote shared outputs/"""
        if not self.ssh:
            QMessageBox.warning(self, "Not connected", "Connect first")
            return
        
        remote = self.shared_path_edit.text().strip()
        if not remote:
            QMessageBox.warning(self, "Missing", "Enter shared remote path")
            return
        
        outdir = remote.rstrip('/') + '/outputs'
        try:
            files = self.ssh.listdir(outdir)
        except:
            self.append_log(f"Cannot list {outdir}")
            return
        
        if not files:
            self.append_log(f"No files in {outdir}")
            return
        
        for f in files:
            r = f"{outdir}/{f}"
            l = LOCAL_JOB_OUTPUT_DIR / f
            try:
                self.append_log(f"Downloading {f}...")
                self.ssh.get(r, str(l))
            except Exception as e:
                self.append_log(f"Failed to download {f}: {e}")
        
        self.append_log(f"✅ Downloaded {len(files)} files to {LOCAL_JOB_OUTPUT_DIR}")

    # ---------- MPI job submission ----------
    def submit_mpi_job(self):
        """Submit a job to OpenMPI cluster"""
        if not self.ssh:
            QMessageBox.warning(self, "Not connected", "Connect first")
            return
        
        local_script = self.script_path.text().strip()
        if not local_script or not Path(local_script).exists():
            QMessageBox.warning(self, "Missing script", "Select a script file")
            return
        
        script_type = self.script_type.currentText()
        remote_base = self.remote_base_path.text().strip()
        hosts_file = self.hosts_file_path.text().strip()
        
        if not Path(hosts_file).exists():
            QMessageBox.warning(self, "Missing hosts file", "Hosts file not found")
            return
        
        self.cfg['remote_base_path'] = remote_base
        self.cfg['hosts_file'] = hosts_file
        save_config(self.cfg)
        
        remote_dir = f"{remote_base}/hpc_jobs"
        script_name = os.path.basename(local_script)
        remote_script = f"{remote_dir}/{script_name}"
        remote_hosts = f"{remote_dir}/hosts.txt"
        
        # Create remote directory
        try:
            self.append_log(f"Preparing remote directory {remote_dir}...")
            self.ssh.exec(f"mkdir -p {remote_dir}")
        except Exception as e:
            self.append_log(f"mkdir failed: {e}")
        
        # Upload script
        try:
            self.ssh.put(local_script, remote_script)
            self.append_log(f"✅ Uploaded {script_name}")
        except Exception as e:
            self.append_log(f"Upload failed: {e}")
            return
        
        # Upload hosts file
        try:
            self.ssh.put(hosts_file, remote_hosts)
        except Exception as e:
            self.append_log(f"Hosts file upload failed: {e}")
            return
        
        # Build MPI command
        num_procs = self.num_procs.value()
        args = self.script_args.text().strip()
        use_gpu = self.use_gpu.isChecked()
        
        job_name = Path(local_script).stem
        timestamp = int(time.time())
        remote_out = f"{remote_dir}/{jobid}.out"
        remote_err = f"{remote_dir}/{jobid}.err"
        
        # Build wrapper script
        if script_type == "Python":
            if use_gpu:
                exec_cmd = f"python3 {remote_script} {args}"
            else:
                exec_cmd = f"python3 {remote_script} {args}"
        elif script_type == "MATLAB":
            matlab_func = Path(local_script).stem
            matlab_call = f"{matlab_func}({args})" if args else f"{matlab_func}()"
            exec_cmd = f"matlab -nodisplay -r \"try, {matlab_call}; catch e, disp(getReport(e)); exit(1); end; exit(0)\""
        else:
            exec_cmd = f"bash {remote_script} {args}"
        
        # Create job launcher script
        launcher_name = f"launch_{jobid}.sh"
        remote_launcher = f"{remote_dir}/{launcher_name}"
        
        mpi_flags = "--mca btl tcp,self --mca pml ob1"
        shared_path = self.shared_path_edit.text().strip()
        shared_export = f"export HPC_SHARED_PATH={shared_path}\n" if shared_path else ""
        
        launcher_content = f""#!/bin/bash

        # Write and upload launcher
        local_launcher = Path.cwd() / launcher_name
        local_launcher.write_text(launcher_content)
        
        try:
            self.ssh.put(str(local_launcher), remote_launcher)
            self.ssh.exec(f"chmod +x {remote_launcher}")
            local_launcher.unlink()
            self.append_log(f"✅ Created job launcher")
        except Exception as e:
            self.append_log(f"Launcher upload failed: {e}")
            try:
                local_launcher.unlink()
            except:
                pass
            return
        
        # Submit job (run in background with nohup)
        try:
            cmd = f"cd {remote_dir} && nohup {remote_launcher} > /dev/null 2>&1 & echo $!"
            out, err = self.ssh.exec(cmd)
            
            if out:
                pid = out.strip()
                self.append_log(f"✅ Job submitted: {jobid} (PID: {pid})")
                
                # Record in database
                nodes_str = ",".join([n['hostname'] for n in self.cluster_nodes[:2]])  # Approximate
                insert_job_record(jobid, job_name, remote_script, remote_out,
                                remote_err, exec_cmd, num_procs, nodes_str, status='RUNNING')
            else:
                self.append_log(f"❌ Job submission failed: {err}")
                insert_job_record(jobid, job_name, remote_script, remote_out,
                                remote_err, exec_cmd, num_procs, "", status='FAILED')
        except Exception as e:
            self.append_log(f"Submit failed: {e}")
            insert_job_record(jobid, job_name, remote_script, remote_out,
                            remote_err, exec_cmd, num_procs, "", status='FAILED')

    def run_custom_mpi_command(self):
        """Run custom MPI command from editor"""
        if not self.ssh:
            QMessageBox.warning(self, "Not connected", "Connect first")
            return
        
        cmd = self.mpi_cmd_editor.toPlainText().strip()
        if not cmd or cmd.startswith('#'):
            QMessageBox.warning(self, "Empty command", "Enter an MPI command")
            return
        
        self.append_log(f"Running: {cmd}")
        try:
            out, err = self.ssh.exec(cmd, timeout=60)
            if out:
                self.append_log("Output:")
                self.append_log(out)
            if err:
                self.append_log("Error:")
                self.append_log(err)
        except Exception as e:
            self.append_log(f"Command failed: {e}")

    # ---------- job monitoring ----------
    def _job_watcher_loop(self):
        """Monitor running jobs and fetch completed outputs"""
        while True:
            try:
                if self.ssh:
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute("SELECT jobid, remote_out, remote_err FROM jobs WHERE status='RUNNING'")
                    rows = c.fetchall()
                    conn.close()
                    
                    for jobid, remote_out, remote_err in rows:
                        if not jobid:
                            continue
                        
                        try:
                            # Check if job is still running by checking if output file exists and is growing
                            remote_dir = os.path.dirname(remote_out)
                            launcher = f"{remote_dir}/launch_{jobid}.sh"
                            
                            # Check if launcher process is still running
                            out, _ = self.ssh.exec(f"pgrep -f {launcher}")
                            
                            if not out.strip():
                                # Job completed
                                self.append_log(f"📥 Job {jobid} completed, fetching outputs...")
                                
                                # Download output files
                                local_out = LOCAL_JOB_OUTPUT_DIR / os.path.basename(remote_out)
                                local_err = LOCAL_JOB_OUTPUT_DIR / os.path.basename(remote_err)
                                
                                try:
                                    self.ssh.get(remote_out, str(local_out))
                                    self.ssh.get(remote_err, str(local_err))
                                    update_job_status(jobid, 'COMPLETED')
                                    self.append_log(f"✅ Downloaded outputs for job {jobid}")
                                except Exception as e:
                                    update_job_status(jobid, 'COMPLETED_NO_OUTPUT')
                                    self.append_log(f"⚠️  Job {jobid} completed but output download failed: {e}")
                        except Exception as e:
                            self.append_log(f"Job watcher error for {jobid}: {e}")
            except Exception as e:
                self.append_log(f"Job watcher loop error: {e}")
            
            time.sleep(JOB_WATCH_INTERVAL)

    # ---------- cluster monitoring ----------
    def _poll_loop(self):
        """Poll cluster status periodically"""
        while self.polling:
            try:
                self.poll_once()
            except Exception as e:
                self.append_log(f"Polling error: {e}")
            time.sleep(POLL_INTERVAL)

    def poll_once(self):
        """Get current cluster status"""
        if not self.ssh:
            return
        
        # Update node stats
        for node in self.cluster_nodes:
            hostname = node['hostname']
            try:
                # Get load average
                out, _ = self.ssh.exec(f"ssh {hostname} 'sysctl -n vm.loadavg'", timeout=5)
                if out:
                    # Parse: { 1.23 2.34 3.45 }
                    loads = re.findall(r'[\d.]+', out)
                    if loads:
                        load_avg = float(loads[0])
                        node['load_avg'] = load_avg
                        
                        # Estimate CPU usage (very rough)
                        cpu_percent = min(100, (load_avg / node['slots']) * 100)
                        
                        # Store in history
                        insert_cluster_stats(datetime.now(), hostname, cpu_percent, 0, load_avg)
            except Exception:
                pass

    # ---------- job history ----------
    def show_job_history(self):
        """Show job history dialog"""
        rows = list_jobs(100)
        
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Job History")
        dlg.resize(900, 500)
        layout = QVBoxLayout()
        
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(["Job ID", "Name", "Status", "Procs", "Nodes", "Submitted", "Script"])
        table.setRowCount(len(rows))
        
        for i, row in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(row[0]))  # jobid
            table.setItem(i, 1, QTableWidgetItem(row[1]))  # name
            table.setItem(i, 2, QTableWidgetItem(row[5]))  # status
            table.setItem(i, 3, QTableWidgetItem(str(row[6])))  # num_procs
            table.setItem(i, 4, QTableWidgetItem(row[7]))  # nodes
            table.setItem(i, 5, QTableWidgetItem(row[4]))  # submitted_at
            table.setItem(i, 6, QTableWidgetItem(os.path.basename(row[2])))  # script
        
        layout.addWidget(table)
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close)
        
        dlg.setLayout(layout)
        dlg.exec_()

def main():
    app = QApplication(sys.argv)
    dash = HPCDashboard()
    dash.show()
    sys.exit(app.exec_())
    
if __name__ == '__main__':
    main()


# ---------- NFS setup guide ----------
# """
# Setting up NFS shared storage (recommended for true shared filesystem):
# On controller (Mac Studio):

# Create shared directory:
# sudo mkdir -p /srv/hpc/shared
# sudo chown $USER:staff /srv/hpc/shared
# sudo chmod 2775 /srv/hpc/shared
# Configure NFS exports:
# sudo nano /etc/exports
# Add line:
# /srv/hpc/shared -alldirs -mapall=$USER:staff 192.168.1.0/24
# Restart NFS:
# sudo nfsd restart

# On each compute node:

# Create mount point:
# sudo mkdir -p /srv/hpc/shared
# Mount NFS share:
# sudo mount -t nfs controller.local:/srv/hpc/shared /srv/hpc/shared
# Make permanent (add to /etc/fstab):
# controller.local:/srv/hpc/shared /srv/hpc/shared nfs auto 0 0

# Then set the dashboard "Shared Path" to /srv/hpc/shared on all nodes.
# """
# ---------- Build macOS app bundle ----------
# """
# To build a standalone macOS application:

# Install PyInstaller:
# pip install pyinstaller
# Create app bundle:
# pyinstaller --name "MacHPCClusterJobScheduler" 
# --windowed 
# --onedir 
# --icon "icon.icns" 
# --collect-all pyqt5 
# --collect-all matplotlib 
# --collect-all paramiko 
# --hidden-import "matplotlib.backends.backend_qt5agg" 
# MacHPCClusterJobScheduler.py
# The app will be in dist/MacHPCClusterJobScheduler.app