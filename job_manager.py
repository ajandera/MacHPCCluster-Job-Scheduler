"""
Fault-tolerant Job Queue Manager for macOS HPC Cluster
Provides Slurm-like job submission and management
"""

import json
import uuid
import subprocess
import time
import os
import signal
import tempfile
import sys
from datetime import datetime


JOB_FILE = "jobs/queue.json"
TIMEOUT = 3600  # Default timeout in seconds


def atomic_write(path, data):
    """
    Atomically write JSON data to file
    Prevents corruption from crashes or interruptions
    """
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except:
        os.unlink(tmp)
        raise


def load_jobs():
    """Load jobs from queue file"""
    if not os.path.exists(JOB_FILE):
        return []
    try:
        with open(JOB_FILE, 'r') as f:
            return json.load(f)
    except:
        return []


def save_jobs(jobs):
    """Save jobs to queue file atomically"""
    atomic_write(JOB_FILE, jobs)


def submit_job(command, name=None, timeout=TIMEOUT):
    """
    Submit a job to the queue
    
    Args:
        command (str): Command to execute
        name (str): Optional job name
        timeout (int): Job timeout in seconds
        
    Returns:
        str: Job ID
    """
    job = {
        "id": str(uuid.uuid4())[:8],
        "name": name or command[:50],
        "cmd": command,
        "state": "queued",
        "pid": None,
        "submit_time": time.time(),
        "start_time": None,
        "end_time": None,
        "timeout": timeout
    }
    
    jobs = load_jobs()
    jobs.append(job)
    save_jobs(jobs)
    
    print(f"✅ Job submitted: {job['id']}")
    print(f"   Name: {job['name']}")
    print(f"   Command: {job['cmd']}")
    return job['id']


def list_jobs(state_filter=None):
    """
    List all jobs, optionally filtered by state
    
    Args:
        state_filter (str): Filter by state (queued, running, finished, failed)
    """
    jobs = load_jobs()
    
    if state_filter:
        jobs = [j for j in jobs if j['state'] == state_filter]
    
    if not jobs:
        print("No jobs found")
        return
    
    print(f"{'ID':<10} {'State':<10} {'Name':<30} {'PID':<8}")
    print("-" * 70)
    for job in jobs:
        pid = str(job.get('pid', '-'))
        print(f"{job['id']:<10} {job['state']:<10} {job['name']:<30} {pid:<8}")


def get_job_info(job_id):
    """Get detailed information about a job"""
    jobs = load_jobs()
    job = next((j for j in jobs if j['id'] == job_id), None)
    
    if not job:
        print(f"❌ Job not found: {job_id}")
        return
    
    print(f"Job ID: {job['id']}")
    print(f"Name: {job['name']}")
    print(f"State: {job['state']}")
    print(f"Command: {job['cmd']}")
    print(f"PID: {job.get('pid', 'N/A')}")
    
    if job.get('submit_time'):
        print(f"Submit Time: {datetime.fromtimestamp(job['submit_time'])}")
    if job.get('start_time'):
        print(f"Start Time: {datetime.fromtimestamp(job['start_time'])}")
    if job.get('end_time'):
        print(f"End Time: {datetime.fromtimestamp(job['end_time'])}")
        duration = job['end_time'] - job['start_time']
        print(f"Duration: {duration:.2f} seconds")


def cancel_job(job_id):
    """Cancel a running or queued job"""
    jobs = load_jobs()
    job = next((j for j in jobs if j['id'] == job_id), None)
    
    if not job:
        print(f"❌ Job not found: {job_id}")
        return
    
    if job['state'] == 'queued':
        job['state'] = 'cancelled'
        save_jobs(jobs)
        print(f"✅ Job {job_id} cancelled (was queued)")
    elif job['state'] == 'running':
        try:
            os.kill(job['pid'], signal.SIGTERM)
            job['state'] = 'cancelled'
            save_jobs(jobs)
            print(f"✅ Job {job_id} cancelled (was running)")
        except:
            print(f"❌ Failed to kill process {job['pid']}")
    else:
        print(f"⚠️  Job {job_id} is {job['state']}, cannot cancel")


def run_jobs():
    """
    Job runner daemon - processes queued jobs
    Run this in the background: python job_manager.py run
    """
    print("🚀 Job runner started")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            jobs = load_jobs()
            
            for job in jobs:
                # Recover orphaned jobs
                if job['state'] == 'running' and job.get('pid'):
                    try:
                        os.kill(job['pid'], 0)  # Check if process exists
                    except OSError:
                        print(f"⚠️  Job {job['id']} orphaned, marking as failed")
                        job['state'] = 'failed'
                        job['end_time'] = time.time()
                        save_jobs(jobs)
                        continue
                
                # Start queued jobs
                if job['state'] == 'queued':
                    print(f"▶️  Starting job {job['id']}: {job['name']}")
                    job['state'] = 'running'
                    job['start_time'] = time.time()
                    
                    # Start process
                    try:
                        p = subprocess.Popen(
                            job['cmd'],
                            shell=True,
                            stdout=open(f"jobs/running/{job['id']}.out", 'w'),
                            stderr=open(f"jobs/running/{job['id']}.err", 'w')
                        )
                        job['pid'] = p.pid
                        save_jobs(jobs)
                        
                        # Wait for completion
                        ret = p.wait()
                        job['end_time'] = time.time()
                        job['state'] = 'finished' if ret == 0 else 'failed'
                        
                        # Move logs
                        os.rename(
                            f"jobs/running/{job['id']}.out",
                            f"jobs/finished/{job['id']}.out"
                        )
                        os.rename(
                            f"jobs/running/{job['id']}.err",
                            f"jobs/finished/{job['id']}.err"
                        )
                        
                        save_jobs(jobs)
                        print(f"✅ Job {job['id']} {job['state']}")
                    except Exception as e:
                        print(f"❌ Job {job['id']} failed to start: {e}")
                        job['state'] = 'failed'
                        job['end_time'] = time.time()
                        save_jobs(jobs)
                
                # Check for timeouts
                if job['state'] == 'running' and job.get('start_time'):
                    elapsed = time.time() - job['start_time']
                    if elapsed > job.get('timeout', TIMEOUT):
                        print(f"⏱️  Job {job['id']} timed out")
                        try:
                            os.kill(job['pid'], signal.SIGKILL)
                        except:
                            pass
                        job['state'] = 'timeout'
                        job['end_time'] = time.time()
                        save_jobs(jobs)
            
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n👋 Job runner stopped")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python job_manager.py submit <command>  - Submit a job")
        print("  python job_manager.py list [state]      - List jobs")
        print("  python job_manager.py info <job_id>     - Job details")
        print("  python job_manager.py cancel <job_id>   - Cancel job")
        print("  python job_manager.py run               - Start job runner")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "submit":
        if len(sys.argv) < 3:
            print("❌ Error: Provide command to run")
            sys.exit(1)
        submit_job(" ".join(sys.argv[2:]))
    
    elif cmd == "list":
        state = sys.argv[2] if len(sys.argv) > 2 else None
        list_jobs(state)
    
    elif cmd == "info":
        if len(sys.argv) < 3:
            print("❌ Error: Provide job ID")
            sys.exit(1)
        get_job_info(sys.argv[2])
    
    elif cmd == "cancel":
        if len(sys.argv) < 3:
            print("❌ Error: Provide job ID")
            sys.exit(1)
        cancel_job(sys.argv[2])
    
    elif cmd == "run":
        run_jobs()
    
    else:
        print(f"❌ Unknown command: {cmd}")
        sys.exit(1)