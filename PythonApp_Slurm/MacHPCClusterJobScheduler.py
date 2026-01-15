#!/usr/bin/env python3
"""
hpc_dashboard_matlab_python_slurm.py

Enhanced HPC Dashboard for macOS with:
- SSH agent & GUI passphrase for encrypted private keys
- Submit MATLAB scripts to SLURM (auto-generate sbatch)
- Submit PYTHON scripts to SLURM with Conda environment support
- Job history (SQLite: ~/.hpc_dashboard.db) and job-watcher
- Shared-folder helpers (NFS guidance + SFTP fallback sync)
- Power history and GPU detection

Dependencies:
    pip install pyqt5 paramiko matplotlib
Run:
    python3 hpc_dashboard_matlab_python_slurm.py
"""
from __future__ import annotations
import sys, os, json, time, re, sqlite3
from datetime import datetime
from pathlib import Path
import threading

import paramiko
from paramiko.agent import Agent
from paramiko.ssh_exception import PasswordRequiredException
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QTextEdit,
    QHBoxLayout, QVBoxLayout, QFileDialog, QMessageBox, QPlainTextEdit,
    QInputDialog, QCheckBox, QSpinBox, QComboBox, QTabWidget
)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# ---------------- constants ----------------
POLL_INTERVAL = 8.0
JOB_WATCH_INTERVAL = 10.0
DB_PATH = Path.home() / 'Documents' / '.MacHPCClusterJobScheduler.db'
CONFIG_PATH = Path.home() / 'Documents'/ '.MacHPCClusterJobScheduler_conf.json'
LOCAL_JOB_OUTPUT_DIR = Path.home() / 'Documents' / 'MacHPCClusterJobScheduler_Outputs' 

# Now it will attempt to create the folder in a writable location
LOCAL_JOB_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------- DB helpers ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jobid TEXT,
            job_type TEXT,
            remote_sbatch TEXT,
            remote_out TEXT,
            submitted_at TEXT,
            status TEXT,
            sbatch_output TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS power_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            power REAL,
            util REAL,
            est_flops REAL
        )
    ''')
    conn.commit(); conn.close()

def insert_job_record(jobid, job_type, remote_sbatch, remote_out, sbatch_output, status='SUBMITTED'):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute('INSERT INTO jobs (jobid, job_type, remote_sbatch, remote_out, submitted_at, status, sbatch_output) VALUES (?, ?, ?, ?, ?, ?, ?)',
              (str(jobid), job_type, remote_sbatch, remote_out, datetime.utcnow().isoformat(), status, sbatch_output))
    conn.commit(); conn.close()

def update_job_status(jobid, new_status):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute('UPDATE jobs SET status=? WHERE jobid=?', (new_status, str(jobid)))
    conn.commit(); conn.close()

def list_jobs(limit=100):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute('SELECT jobid, job_type, remote_sbatch, remote_out, submitted_at, status FROM jobs ORDER BY id DESC LIMIT ?', (limit,))
    rows = c.fetchall(); conn.close(); return rows

def insert_power(ts, power, util, est_flops=None):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute('INSERT INTO power_history (ts, power, util, est_flops) VALUES (?, ?, ?, ?)', (ts.isoformat(), power, util, est_flops))
    conn.commit(); conn.close()

# ---------- config ----------
def load_config():
    if CONFIG_PATH.exists():
        try: return json.loads(CONFIG_PATH.read_text())
        except: return {}
    return {}

def save_config(cfg):
    try: CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except: pass

# ---------- SSH helper ----------
class SSHClientEnhanced:
    def __init__(self, hostname, username, key_path=None, password=None, port=22, passphrase_callback=None):
        self.hostname = hostname; self.username = username; self.key_path = key_path
        self.password = password; self.port = port; self.passphrase_callback = passphrase_callback
        self.client = None; self.sftp = None

    def _load_private_key(self, path):
        last_exc = None
        for KeyClass in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey):
            try:
                return KeyClass.from_private_key_file(path)
            except PasswordRequiredException as e:
                last_exc = e
                if self.passphrase_callback:
                    pw = self.passphrase_callback()
                    if pw is None: raise RuntimeError('Passphrase canceled')
                    try: return KeyClass.from_private_key_file(path, password=pw)
                    except Exception as e2: last_exc = e2; continue
                else: raise
            except Exception as e:
                last_exc = e; continue
        if last_exc: raise last_exc
        return None

    def connect(self, timeout=12):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = None
        if self.key_path:
            pkey = self._load_private_key(self.key_path)
        try:
            if pkey: self.client.connect(self.hostname, port=self.port, username=self.username, pkey=pkey, timeout=timeout)
            elif self.password: self.client.connect(self.hostname, port=self.port, username=self.username, password=self.password, timeout=timeout)
            else:
                try:
                    agent = Agent(); keys = agent.get_keys()
                    if keys:
                        connected=False; last_exc=None
                        for k in keys:
                            try:
                                self.client.connect(self.hostname, port=self.port, username=self.username, pkey=k, timeout=timeout)
                                connected=True; break
                            except Exception as e: last_exc=e
                        if not connected:
                            self.client.connect(self.hostname, port=self.port, username=self.username, timeout=timeout)
                    else:
                        self.client.connect(self.hostname, port=self.port, username=self.username, timeout=timeout)
                except Exception:
                    self.client.connect(self.hostname, port=self.port, username=self.username, timeout=timeout)
            self.sftp = self.client.open_sftp()
        except Exception as e:
            raise RuntimeError(f"SSH connect failed: {e}")

    def exec(self, cmd, timeout=20):
        if self.client is None: raise RuntimeError("Not connected")
        stdin, stdout, stderr = self.client.exec_command(cmd, timeout=timeout)
        return stdout.read().decode('utf-8', errors='ignore').strip(), stderr.read().decode('utf-8', errors='ignore').strip()

    def put(self, local_path, remote_path):
        if self.sftp is None: raise RuntimeError("SFTP not connected")
        self.sftp.put(local_path, remote_path)

    def get(self, remote_path, local_path):
        if self.sftp is None: raise RuntimeError("SFTP not connected")
        self.sftp.get(remote_path, local_path)

    def listdir(self, remote_path):
        if self.sftp is None: raise RuntimeError("SFTP not connected")
        try: return self.sftp.listdir(remote_path)
        except Exception: return []

    def mkdir(self, remote_path):
        if self.sftp is None: raise RuntimeError("SFTP not connected")
        try: self.sftp.mkdir(remote_path)
        except Exception: pass

    def close(self):
        try: 
            if self.sftp: self.sftp.close()
        except: pass
        try:
            if self.client: self.client.close()
        except: pass
        self.client=None; self.sftp=None

# ---------- plotting ----------
class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=6, height=2.5, dpi=100):
        fig = Figure(figsize=(width,height), dpi=dpi)
        self.ax = fig.add_subplot(111)
        super().__init__(fig)
        fig.tight_layout(pad=4.5)

# ---------- main GUI ----------
class HPCDashboard(QWidget):
    def __init__(self):
        super().__init__()
        init_db()
        self.cfg = load_config()
        self.ssh = None
        self.polling=False
        self.poll_thread=None
        self.job_watcher_thread=None
        self.power_history=[]
        self.max_history=300
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("HPC Job Scheduler - MATLAB & Python")
        self.resize(1400,900)

        # Main horizontal layout - left and right columns
        main_horizontal = QHBoxLayout()
        
        # LEFT COLUMN - Main controls
        left_column = QVBoxLayout()
        
        # connection row
        self.host_edit = QLineEdit(self.cfg.get('host',''))
        self.user_edit = QLineEdit(self.cfg.get('user',''))
        self.key_edit = QLineEdit(self.cfg.get('key_path',''))
        btn_browse_key = QPushButton("Browse")
        btn_browse_key.clicked.connect(self.browse_key)
        btn_connect = QPushButton("Connect"); btn_connect.clicked.connect(self.connect_clicked)
        btn_disconnect = QPushButton("Disconnect"); btn_disconnect.clicked.connect(self.disconnect_clicked)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Host:")); row1.addWidget(self.host_edit)
        row1.addWidget(QLabel("User:")); row1.addWidget(self.user_edit)
        row1.addWidget(QLabel("Key:")); row1.addWidget(self.key_edit)
        row1.addWidget(btn_browse_key); row1.addWidget(btn_connect); row1.addWidget(btn_disconnect)

        # quick actions
        btn_sinfo=QPushButton("sinfo -Nel"); btn_sinfo.clicked.connect(lambda: self.run_command_and_append("sinfo -Nel"))
        btn_squeue=QPushButton("squeue -u $USER"); btn_squeue.clicked.connect(lambda: self.run_command_and_append("squeue -u $USER"))
        btn_refresh=QPushButton("Refresh"); btn_refresh.clicked.connect(self.poll_once)
        btn_history=QPushButton("Job History"); btn_history.clicked.connect(self.show_job_history)
        btn_row = QHBoxLayout(); btn_row.addWidget(btn_sinfo); btn_row.addWidget(btn_squeue)
        btn_row.addWidget(btn_refresh); btn_row.addWidget(btn_history)

        # shared folder controls
        self.shared_path_edit = QLineEdit(self.cfg.get('shared_path','/srv/hpc/shared'))
        btn_ensure_shared = QPushButton("Ensure shared folder"); btn_ensure_shared.clicked.connect(self.ensure_shared_folder)
        btn_fetch_shared = QPushButton("Fetch shared results"); btn_fetch_shared.clicked.connect(self.fetch_shared_results)
        btn_sync_remote = QPushButton("Sync outputs from remote"); btn_sync_remote.clicked.connect(self.sync_outputs_from_remote)
        shared_row = QHBoxLayout()
        shared_row.addWidget(QLabel("Shared (remote):")); shared_row.addWidget(self.shared_path_edit)
        shared_row.addWidget(btn_ensure_shared); shared_row.addWidget(btn_fetch_shared); shared_row.addWidget(btn_sync_remote)

        # Create tabs for MATLAB and Python
        self.tab_widget = QTabWidget()
        
        # MATLAB tab
        matlab_tab = QWidget()
        matlab_layout = QVBoxLayout()
        
        self.remote_base_path = QLineEdit(self.cfg.get('remote_base_path', f"/home/{os.getlogin()}"))
        self.matlab_script_path = QLineEdit()
        btn_browse_m = QPushButton("Browse .m"); btn_browse_m.clicked.connect(self.browse_matlab_script)
        self.matlab_use_gpu = QCheckBox("Use GPU")
        self.matlab_cpus = QSpinBox(); self.matlab_cpus.setRange(1,128); self.matlab_cpus.setValue(4)
        self.matlab_mem = QLineEdit("8G")
        self.matlab_args = QLineEdit()
        btn_submit_matlab = QPushButton("Submit MATLAB Job"); btn_submit_matlab.clicked.connect(self.submit_matlab_job)

        matlab_row1 = QHBoxLayout()
        matlab_row1.addWidget(QLabel("Remote base:")); matlab_row1.addWidget(self.remote_base_path)
        
        matlab_row2 = QHBoxLayout()
        matlab_row2.addWidget(QLabel("Script:")); matlab_row2.addWidget(self.matlab_script_path)
        matlab_row2.addWidget(btn_browse_m)
        
        matlab_row3 = QHBoxLayout()
        matlab_row3.addWidget(self.matlab_use_gpu); matlab_row3.addWidget(QLabel("CPUs:"))
        matlab_row3.addWidget(self.matlab_cpus); matlab_row3.addWidget(QLabel("Mem:"))
        matlab_row3.addWidget(self.matlab_mem); matlab_row3.addWidget(QLabel("Args:"))
        matlab_row3.addWidget(self.matlab_args); matlab_row3.addWidget(btn_submit_matlab)

        matlab_layout.addLayout(matlab_row1)
        matlab_layout.addLayout(matlab_row2)
        matlab_layout.addLayout(matlab_row3)
        matlab_tab.setLayout(matlab_layout)

        # Python tab
        python_tab = QWidget()
        python_layout = QVBoxLayout()
        
        self.python_script_path = QLineEdit()
        btn_browse_py = QPushButton("Browse .py"); btn_browse_py.clicked.connect(self.browse_python_script)
        self.python_use_gpu = QCheckBox("Use GPU")
        self.python_cpus = QSpinBox(); self.python_cpus.setRange(1,128); self.python_cpus.setValue(4)
        self.python_mem = QLineEdit("8G")
        self.python_conda_env = QLineEdit(self.cfg.get('conda_env','base'))
        self.python_conda_path = QLineEdit(self.cfg.get('conda_path','~/miniconda3'))
        self.python_args = QLineEdit()
        self.python_requirements = QLineEdit()
        self.python_env_yaml = QLineEdit()
        btn_browse_yaml = QPushButton("Browse YAML")
        btn_browse_yaml.clicked.connect(self.browse_env_yaml)
        btn_submit_python = QPushButton("Submit Python Job"); btn_submit_python.clicked.connect(self.submit_python_job)

        python_row1 = QHBoxLayout()
        python_row1.addWidget(QLabel("Conda path:")); python_row1.addWidget(self.python_conda_path)
        python_row1.addWidget(QLabel("Conda env:")); python_row1.addWidget(self.python_conda_env)
        
        python_row2 = QHBoxLayout()
        python_row2.addWidget(QLabel("Script:")); python_row2.addWidget(self.python_script_path)
        python_row2.addWidget(btn_browse_py)
        
        python_row3 = QHBoxLayout()
        python_row3.addWidget(self.python_use_gpu); python_row3.addWidget(QLabel("CPUs:"))
        python_row3.addWidget(self.python_cpus); python_row3.addWidget(QLabel("Mem:"))
        python_row3.addWidget(self.python_mem)
        
        python_row4 = QHBoxLayout()
        python_row4.addWidget(QLabel("Script args:")); python_row4.addWidget(self.python_args)
        
        python_row5 = QHBoxLayout()
        python_row5.addWidget(QLabel("Pip requirements:")); python_row5.addWidget(self.python_requirements)
        
        python_row6 = QHBoxLayout()
        python_row6.addWidget(QLabel("Conda env YAML (optional):")); python_row6.addWidget(self.python_env_yaml)
        python_row6.addWidget(btn_browse_yaml); python_row6.addWidget(btn_submit_python)

        python_layout.addLayout(python_row1)
        python_layout.addLayout(python_row2)
        python_layout.addLayout(python_row3)
        python_layout.addLayout(python_row4)
        python_layout.addLayout(python_row5)
        python_layout.addLayout(python_row6)
        python_tab.setLayout(python_layout)

        # Add tabs
        self.tab_widget.addTab(matlab_tab, "MATLAB Jobs")
        self.tab_widget.addTab(python_tab, "Python Jobs")

        # Add all left column widgets
        left_column.addLayout(row1)
        left_column.addLayout(btn_row)
        left_column.addLayout(shared_row)
        left_column.addWidget(self.tab_widget)
        
        # RIGHT COLUMN - Chart, Job Editor, and Log
        right_column = QVBoxLayout()
        
        # chart
        self.canvas = MplCanvas(self, width=6, height=3); 
        self.canvas.ax.set_title("Power/Util/TFLOPS")
        self.canvas.plot_line_power, = self.canvas.ax.plot([], [], label='Power')
        self.canvas.plot_line_util, = self.canvas.ax.plot([], [], label='Util')
        self.canvas.plot_line_flops, = self.canvas.ax.plot([], [], label='Est TFLOPS')
        self.canvas.ax.legend()

        # advanced job editor
        self.job_editor = QTextEdit()
        self.job_editor.setPlainText("# advanced sbatch editor")
        self.job_editor.setMaximumHeight(200)
        
        # log
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)

        right_column.addWidget(QLabel("Cluster Monitoring:"))
        right_column.addWidget(self.canvas)
        right_column.addWidget(QLabel("Advanced job script editor:"))
        right_column.addWidget(self.job_editor)
        right_column.addWidget(QLabel("Log:"))
        right_column.addWidget(self.log)
        
        # Combine left and right columns with stretch factors
        main_horizontal.addLayout(left_column, stretch=3)
        main_horizontal.addLayout(right_column, stretch=2)
        
        # Set main layout
        self.setLayout(main_horizontal)

    # ---------- UI helpers ----------
    def browse_key(self):
        p,_ = QFileDialog.getOpenFileName(self, "Select private key", str(Path.home()))
        if p: self.key_edit.setText(p)

    def browse_matlab_script(self):
        p,_ = QFileDialog.getOpenFileName(self, "Select MATLAB script", str(Path.home()), "MATLAB Files (*.m)")
        if p: self.matlab_script_path.setText(p)

    def browse_python_script(self):
        p,_ = QFileDialog.getOpenFileName(self, "Select Python script", str(Path.home()), "Python Files (*.py)")
        if p: self.python_script_path.setText(p)

    def browse_env_yaml(self):
        p,_ = QFileDialog.getOpenFileName(self, "Select Conda environment YAML", str(Path.home()), "YAML Files (*.yml *.yaml)")
        if p: self.python_env_yaml.setText(p)

    def append_log(self, text):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S"); self.log.appendPlainText(f"[{ts}] {text}")

    def _ask_passphrase(self):
        pw, ok = QInputDialog.getText(self, 'SSH passphrase', 'Enter passphrase:', QLineEdit.Password)
        return pw if ok else None

    # ---------- connection ----------
    def connect_clicked(self):
        host = self.host_edit.text().strip(); user = self.user_edit.text().strip(); key = self.key_edit.text().strip() or None
        if not host or not user:
            QMessageBox.warning(self, "Missing", "Enter host and user"); return
        self.append_log(f"Connecting {user}@{host} ...")
        try:
            self.ssh = SSHClientEnhanced(host, user, key_path=key, passphrase_callback=self._ask_passphrase)
            self.ssh.connect()
        except Exception as e:
            self.append_log(f"Connect failed: {e}"); QMessageBox.critical(self, "SSH", str(e)); self.ssh=None; return
        self.append_log("Connected")
        self.cfg['host']=host; self.cfg['user']=user; self.cfg['key_path']=key; save_config(self.cfg)
        if not getattr(self,'polling',False):
            self.polling=True; self.poll_thread=threading.Thread(target=self._poll_loop, daemon=True); self.poll_thread.start()
        if not getattr(self,'job_watcher_thread',None):
            self.job_watcher_thread = threading.Thread(target=self._job_watcher_loop, daemon=True); self.job_watcher_thread.start()
        self._check_remote_gpu_availability()
        self._check_conda_availability()

    def disconnect_clicked(self):
        self.append_log("Disconnecting..."); self.polling=False
        if self.ssh:
            try: self.ssh.close()
            except: pass
        self.ssh=None; self.append_log("Disconnected")

    def run_command_and_append(self, cmd):
        if not self.ssh:
            QMessageBox.warning(self, "Not connected", "Please connect first"); return
        try:
            out, err = self.ssh.exec(cmd)
            if out: self.append_log(out)
            if err: self.append_log("ERR: "+err)
        except Exception as e:
            self.append_log("Command failed: "+str(e))

    # ---------- SHARED FOLDER helpers ----------
    def ensure_shared_folder(self):
        """Create remote shared path and subfolders (inputs/outputs/tmp/locks)."""
        if not self.ssh:
            QMessageBox.warning(self, "Not connected", "Connect first"); return
        remote = self.shared_path_edit.text().strip()
        if not remote:
            QMessageBox.warning(self, "Missing", "Enter shared remote path"); return
        try:
            self.append_log(f"Creating remote folder {remote} ...")
            self.ssh.exec(f"mkdir -p {remote} && chmod 2775 {remote} || true")
            for d in ('inputs','outputs','tmp','locks'):
                self.ssh.mkdir(f"{remote}/{d}")
            self.append_log("Shared path created (note: export via NFS is recommended for true shared FS)")
            self.cfg['shared_path']=remote; save_config(self.cfg)
        except Exception as e:
            self.append_log("ensure_shared_folder failed: "+str(e))

    def _remote_list_shared_outputs(self):
        if not self.ssh: return []
        remote = self.shared_path_edit.text().strip()
        if not remote: return []
        outdir = remote.rstrip('/') + '/outputs'
        try: return self.ssh.listdir(outdir)
        except: return []

    def fetch_shared_results(self):
        """Download all files from remote shared outputs/ to local ./hpc_job_outputs/"""
        if not self.ssh:
            QMessageBox.warning(self, "Not connected", "Connect first"); return
        remote = self.shared_path_edit.text().strip()
        if not remote:
            QMessageBox.warning(self, "Missing", "Enter shared remote path"); return
        outdir = remote.rstrip('/') + '/outputs'
        files = self._remote_list_shared_outputs()
        if not files:
            self.append_log(f"No files in {outdir}")
            return
        for f in files:
            r = f"{outdir}/{f}"; l = LOCAL_JOB_OUTPUT_DIR / f
            try:
                self.append_log(f"Downloading {r} -> {l}")
                self.ssh.get(r, str(l))
            except Exception as e:
                self.append_log(f"Failed to download {r}: {e}")
        self.append_log("Fetch complete")

    def sync_outputs_from_remote(self):
        # currently a convenience wrapper around fetch_shared_results
        self.fetch_shared_results()

    # ---------- PYTHON job submission ----------
    def submit_python_job(self):
        if not self.ssh:
            QMessageBox.warning(self,"Not connected","Connect first"); return
        local_py = self.python_script_path.text().strip()
        if not local_py or not Path(local_py).is_file():
            QMessageBox.warning(self,"Missing script","Select a local .py file"); return
        
        remote_base = self.remote_base_path.text().strip() or f"/home/{self.user_edit.text().strip()}"
        self.cfg['remote_base_path']=remote_base
        conda_env = self.python_conda_env.text().strip()
        conda_path = self.python_conda_path.text().strip()
        # Expand ~ for remote commands
        conda_path_expanded = conda_path.replace('~', f'/home/{self.user_edit.text().strip()}')
        self.cfg['conda_env']=conda_env
        self.cfg['conda_path']=conda_path
        save_config(self.cfg)
        
        remote_dir = f"{remote_base}/hpc_jobs"
        remote_py = f"{remote_dir}/{os.path.basename(local_py)}"
        
        try:
            self.append_log(f"Ensuring remote dir {remote_dir} ...")
            self.ssh.exec(f"mkdir -p {remote_dir}")
        except Exception as e:
            self.append_log("mkdir failed: "+str(e))
        
        # upload .py
        try:
            tmp = Path.cwd() / f"tmp_{int(time.time())}_{os.path.basename(local_py)}"
            tmp.write_bytes(Path(local_py).read_bytes())
            self.ssh.put(str(tmp), remote_py); tmp.unlink()
            self.append_log(f"Uploaded {remote_py}")
        except Exception as e:
            self.append_log("Upload failed: "+str(e)); return
        
        # Handle optional environment YAML
        env_yaml_path = self.python_env_yaml.text().strip()
        env_setup_commands = ""
        
        if env_yaml_path and Path(env_yaml_path).is_file():
            # Upload YAML and create environment from it
            remote_yaml = f"{remote_dir}/environment_{int(time.time())}.yml"
            try:
                tmp_yaml = Path.cwd() / f"tmp_{int(time.time())}.yml"
                tmp_yaml.write_bytes(Path(env_yaml_path).read_bytes())
                self.ssh.put(str(tmp_yaml), remote_yaml); tmp_yaml.unlink()
                self.append_log(f"Uploaded environment YAML {remote_yaml}")
                
                # Create temp environment from YAML
                temp_env_name = f"{conda_env}_job_{int(time.time())}"
                env_setup_commands = f"""
# Create environment from YAML
{conda_path_expanded}/bin/conda env create -f {remote_yaml} -n {temp_env_name} || true
eval "$({conda_path_expanded}/bin/conda shell.bash hook)"
conda activate {temp_env_name}
"""
                conda_env = temp_env_name  # Use the temp environment
            except Exception as e:
                self.append_log(f"YAML upload failed: {e}")
        else:
            # Standard conda activation
            env_setup_commands = f"""
# Initialize conda (PERUN method)
eval "$({conda_path_expanded}/bin/conda shell.bash hook)"
conda activate {conda_env}
"""
        
        # build sbatch
        cpus = int(self.python_cpus.value())
        mem = self.python_mem.text().strip() or "8G"
        use_gpu = bool(self.python_use_gpu.isChecked())
        args = self.python_args.text().strip()
        requirements = self.python_requirements.text().strip()
        
        script_basename = Path(local_py).stem
        gpu_line = "#SBATCH --gres=gpu:1\n" if use_gpu else ""
        sbatch_name = f"{script_basename}_job_{int(time.time())}.sh"
        remote_sbatch = f"{remote_dir}/{sbatch_name}"
        remote_out = f"{remote_dir}/{script_basename}_%j.out"
        
        shared = self.shared_path_edit.text().strip()
        shared_export = f"export HPC_SHARED_PATH={shared}\n" if shared else ""
        
        # Optional pip install requirements
        req_install = ""
        if requirements:
            req_install = f"pip install {requirements}\n"
        
        # Build python command with args
        python_cmd = f"python {os.path.basename(local_py)}"
        if args:
            python_cmd += f" {args}"
        
        sbatch_content = f"""#!/bin/bash
#SBATCH --job-name={script_basename}
#SBATCH --partition=CPU
#SBATCH --output={script_basename}_%j.out
#SBATCH --time=24:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={mem}
{gpu_line}
{env_setup_commands}
cd {remote_dir}
{shared_export}
{req_install}
{python_cmd}
"""
        
        local_sbatch = Path.cwd() / sbatch_name
        local_sbatch.write_text(sbatch_content)
        
        try:
            self.ssh.put(str(local_sbatch), remote_sbatch)
            local_sbatch.unlink()
            self.append_log(f"Uploaded sbatch {remote_sbatch}")
            
            out, err = self.ssh.exec(f"sbatch {remote_sbatch}")
            if out:
                self.append_log(out)
                m = re.search(r"Submitted batch job (\d+)", out)
                jobid = m.group(1) if m else None
                insert_job_record(jobid, 'PYTHON', remote_sbatch, remote_out, out, 
                                status='SUBMITTED' if jobid else 'SUBMIT_FAILED')
            else:
                self.append_log("ERR: "+err)
                insert_job_record(None, 'PYTHON', remote_sbatch, remote_out, err, 
                                status='SUBMIT_FAILED')
        except Exception as e:
            self.append_log("Submit failed: "+str(e))
            insert_job_record(None, 'PYTHON', remote_sbatch, remote_out, str(e), 
                            status='SUBMIT_FAILED')
            try: local_sbatch.unlink()
            except: pass

    # ---------- MATLAB job submission ----------
    def submit_matlab_job(self):
        if not self.ssh:
            QMessageBox.warning(self,"Not connected","Connect first"); return
        local_m = self.matlab_script_path.text().strip()
        if not local_m or not Path(local_m).is_file():
            QMessageBox.warning(self,"Missing script","Select a local .m file"); return
        remote_base = self.remote_base_path.text().strip() or f"/home/{self.user_edit.text().strip()}"
        self.cfg['remote_base_path']=remote_base; save_config(self.cfg)
        remote_dir = f"{remote_base}/hpc_jobs"
        remote_m = f"{remote_dir}/{os.path.basename(local_m)}"
        try:
            self.append_log(f"Ensuring remote dir {remote_dir} ..."); self.ssh.exec(f"mkdir -p {remote_dir}")
        except Exception as e:
            self.append_log("mkdir failed: "+str(e))
        # upload .m
        try:
            tmp = Path.cwd() / f"tmp_{int(time.time())}_{os.path.basename(local_m)}"
            tmp.write_bytes(Path(local_m).read_bytes())
            self.ssh.put(str(tmp), remote_m); tmp.unlink()
            self.append_log(f"Uploaded {remote_m}")
        except Exception as e:
            self.append_log("Upload failed: "+str(e)); return
        # build sbatch
        cpus = int(self.matlab_cpus.value()); mem = self.matlab_mem.text().strip() or "8G"
        use_gpu = bool(self.matlab_use_gpu.isChecked()); args = self.matlab_args.text().strip()
        script_basename = Path(local_m).stem
        gpu_line = "#SBATCH --gres=gpu:1\n" if use_gpu else ""
        sbatch_name = f"{script_basename}_job_{int(time.time())}.sh"
        remote_sbatch = f"{remote_dir}/{sbatch_name}"; remote_out = f"{remote_dir}/{script_basename}_%j.out"
        shared = self.shared_path_edit.text().strip()
        shared_export = f"export HPC_SHARED_PATH={shared}\n" if shared else ""
        matlab_call = f"{script_basename}({args})" if args else f"{script_basename}()"
        sbatch_content = f"""#!/bin/bash
#SBATCH --job-name={script_basename}
#SBATCH --partition=CPU
#SBATCH --output={script_basename}_%j.out
#SBATCH --time=24:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={mem}
{gpu_line}
module load matlab/R2025b || true
cd {remote_dir}
{shared_export}
matlab -nodisplay -r "try, {matlab_call}; catch e, disp(getReport(e)); exit(1); end; exit(0)"
"""
        local_sbatch = Path.cwd() / sbatch_name; local_sbatch.write_text(sbatch_content)
        try:
            self.ssh.put(str(local_sbatch), remote_sbatch); local_sbatch.unlink()
            self.append_log(f"Uploaded sbatch {remote_sbatch}")
            out, err = self.ssh.exec(f"sbatch {remote_sbatch}")
            if out:
                self.append_log(out)
                m = re.search(r"Submitted batch job (\d+)", out)
                jobid = m.group(1) if m else None
                insert_job_record(jobid, 'MATLAB', remote_sbatch, remote_out, out, status='SUBMITTED' if jobid else 'SUBMIT_FAILED')
            else:
                self.append_log("ERR: "+err); insert_job_record(None, 'MATLAB', remote_sbatch, remote_out, err, status='SUBMIT_FAILED')
        except Exception as e:
            self.append_log("Submit failed: "+str(e)); insert_job_record(None, 'MATLAB', remote_sbatch, remote_out, str(e), status='SUBMIT_FAILED')
            try: local_sbatch.unlink()
            except: pass

    # ---------- job watcher ----------
    def _job_watcher_loop(self):
        while True:
            try:
                if self.ssh:
                    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                    c.execute("SELECT jobid, remote_out FROM jobs WHERE status='SUBMITTED'")
                    rows = c.fetchall(); conn.close()
                    for jobid, remote_out in rows:
                        if not jobid:
                            update_job_status(jobid, 'SUBMIT_FAILED'); continue
                        try:
                            out, err = self.ssh.exec(f"squeue -j {jobid} -h")
                            if not out.strip():
                                remote_out_path = remote_out.replace('%j', str(jobid))
                                local_target = LOCAL_JOB_OUTPUT_DIR / Path(remote_out_path).name
                                self.append_log(f"Job {jobid} finished — fetching {remote_out_path} -> {local_target}")
                                try:
                                    self.ssh.get(remote_out_path, str(local_target)); update_job_status(jobid, 'COMPLETED')
                                    self.append_log(f"Downloaded output for job {jobid} to {local_target}")
                                except Exception as e:
                                    # try get from shared outputs if configured
                                    shared = self.shared_path_edit.text().strip()
                                    if shared:
                                        cand = f"{shared}/outputs/{jobid}.out"
                                        try:
                                            self.ssh.get(cand, str(local_target)); update_job_status(jobid, 'COMPLETED')
                                            self.append_log(f"Downloaded output for job {jobid} from shared folder")
                                            continue
                                        except: pass
                                    update_job_status(jobid, 'FINISHED_NO_OUTPUT'); self.append_log(f"Could not download output for {jobid}: {e}")
                        except Exception as e:
                            self.append_log("Job watcher squeue failed: "+str(e))
            except Exception as e:
                self.append_log("Job watcher loop error: "+str(e))
            time.sleep(JOB_WATCH_INTERVAL)

    # ---------- polling ----------
    def _poll_loop(self):
        while self.polling:
            try: self.poll_once()
            except Exception as e: self.append_log("Polling error: "+str(e))
            time.sleep(POLL_INTERVAL)

    def poll_once(self):
        if not self.ssh: return
        try:
            out, err = self.ssh.exec("sinfo -Nel")
            if out: self.append_log(out)
        except Exception as e: self.append_log("sinfo err: "+str(e))

    def _check_remote_gpu_availability(self):
        if not self.ssh: return
        try:
            out, err = self.ssh.exec("which nvidia-smi && nvidia-smi --query-gpu=name --format=csv,noheader,nounits || true", timeout=8)
            if out and 'nvidia-smi' in out:
                self.append_log("nvidia-smi found; GPU enabled")
                self.matlab_use_gpu.setEnabled(True)
                self.python_use_gpu.setEnabled(True)
            else:
                self.append_log("nvidia-smi not found; GPU disabled")
                self.matlab_use_gpu.setEnabled(False); self.matlab_use_gpu.setChecked(False)
                self.python_use_gpu.setEnabled(False); self.python_use_gpu.setChecked(False)
        except Exception:
            self.append_log("nvidia-smi check failed")
            self.matlab_use_gpu.setEnabled(False); self.matlab_use_gpu.setChecked(False)
            self.python_use_gpu.setEnabled(False); self.python_use_gpu.setChecked(False)

    def _check_conda_availability(self):
        if not self.ssh: return
        conda_path = self.python_conda_path.text().strip()
        # Expand ~ to actual home directory
        expanded_path = conda_path.replace('~', f'/home/{self.user_edit.text().strip()}')
        try:
            out, err = self.ssh.exec(f"test -d {expanded_path} && echo 'FOUND' || echo 'NOT_FOUND'", timeout=8)
            if 'FOUND' in out:
                self.append_log(f"Conda found at {conda_path}")
                # List available environments using conda info
                out2, err2 = self.ssh.exec(f"{expanded_path}/bin/conda env list", timeout=10)
                if out2:
                    self.append_log(f"Available conda environments:\n{out2}")
            else:
                self.append_log(f"WARNING: Conda not found at {conda_path}")
                QMessageBox.warning(self, "Conda not found", 
                    f"Conda was not found at {conda_path}.\nPlease update the Conda path in the Python tab.\n\nFor PERUN, Conda should be installed at ~/miniconda3")
        except Exception as e:
            self.append_log(f"Conda check failed: {e}")

    # ---------- job history UI ----------
    def show_job_history(self):
        rows = list_jobs(200)
        text = '\n'.join([f"[{r[0]}] type={r[1]} status={r[5]} at {r[4]}\n  sbatch={r[2]}\n  output={r[3]}\n" for r in rows])
        dlg = QtWidgets.QDialog(self); dlg.setWindowTitle("Job history"); dlg.resize(800, 600)
        layout=QVBoxLayout()
        te = QPlainTextEdit(); te.setPlainText(text); te.setReadOnly(True); layout.addWidget(te)
        btn = QPushButton("Close"); btn.clicked.connect(dlg.accept); layout.addWidget(btn)
        dlg.setLayout(layout); dlg.exec_()

# ---------- run ----------
def main():
    app = QApplication(sys.argv)
    dash = HPCDashboard(); dash.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()

# ---------- NFS quick guide (use this for true shared FS) ----------
# On controller:
# sudo mkdir -p /srv/hpc/shared
# sudo chown youruser:staff /srv/hpc/shared
# sudo chmod 2775 /srv/hpc/shared
# add to /etc/exports:
# /srv/hpc/shared -alldirs -mapall=youruser:staff 192.168.1.0/24
# sudo nfsd restart
# On each compute node:
# sudo mkdir -p /srv/hpc/shared
# sudo mount -t nfs controller:/srv/hpc/shared /srv/hpc/shared
#
# Then set the dashboard "Shared (remote)" path to the same path (/srv/hpc/shared).
#
# If NFS is not an option the dashboard SFTP helpers let you copy outputs back
# to your mac for collection (slower, but works).

# ---------- Python/Conda setup guide for PERUN ----------
# On PERUN HPC cluster, install miniconda3 following the official wiki:
# https://wiki.perun.tuke.sk/env/conda/
#
# Quick installation:
# mkdir -p ~/miniconda3
# wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh
# bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
# ~/miniconda3/bin/conda init bash
# source ~/.bashrc
#
# Create a custom environment:
# conda create -n myenv python=3.11
# conda activate myenv
# conda install -c conda-forge numpy pandas scipy matplotlib
#
# For deep learning with GPU (PyTorch example):
# conda create -n pytorch python=3.11
# conda activate pytorch
# conda install pytorch torchvision torchaudio pytorch-cuda=11.8 -c pytorch -c nvidia
#
# For TensorFlow with GPU:
# conda create -n tensorflow python=3.11
# conda activate tensorflow
# conda install -c conda-forge cudatoolkit=11.8 cudnn=8.6
# pip install tensorflow[and-cuda]
#
# Then in the dashboard, set:
# - Conda path: ~/miniconda3
# - Conda env: myenv (or pytorch, tensorflow, etc.)
#
# Export environment for reproducibility:
# conda env export --from-history > myenv.yml
#
# Monitor disk usage (Conda can consume significant space):
# du -sh ~/miniconda3
# conda clean --all  # Clean cache if needed

# Bundle to macOS app
# pyinstaller --name "MacHPCClusterJobScheduler" \
#             --windowed \
#             --onedir \
#             --icon "HPCDashboard.icns" \
#             --collect-all pyqt5 \
#             --collect-all matplotlib \
#             --collect-all paramiko \
#             --hidden-import "matplotlib.backends.backend_qt5agg" \
#             MacHPCClusterJobScheduler.py