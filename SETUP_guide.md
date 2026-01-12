# Step-by-Step Setup Guide

Complete walkthrough for setting up your macOS HPC cluster from scratch.

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] 2+ Mac computers on the same network
- [ ] Admin access on all machines
- [ ] Network connectivity between machines
- [ ] 30-60 minutes for setup

## Part 1: Controller Node Setup (Mac Studio)

### Step 1.1: Install Dependencies

```bash
# Clone repository
git clone https://github.com/yourusername/macos-hpc-cluster.git
cd macos-hpc-cluster

# Run installation
chmod +x install.sh
./install.sh
```

**Expected output:** Installation Complete!

### Step 1.2: Configure SSH Keys

```bash
# Generate SSH key (press Enter for all prompts)
ssh-keygen -t ed25519 -C "hpc-cluster"

# Your key is now in ~/.ssh/id_ed25519
```

### Step 1.3: Note Your Hostname

```bash
hostname
# Example output: mac-studio.local
```

Write this down: `____________________`

## Part 2: Compute Node Setup (Mac Pro)

### Step 2.1: Install on Compute Node

**On your Mac Pro:**

```bash
git clone https://github.com/yourusername/macos-hpc-cluster.git
cd macos-hpc-cluster
chmod +x install.sh
./install.sh
```

### Step 2.2: Note Compute Node Hostname

```bash
hostname
# Example output: mac-pro.local
```

Write this down: `____________________`

### Step 2.3: Copy SSH Key from Controller

**Back on Mac Studio (controller):**

```bash
# Replace with your actual compute node hostname
ssh-copy-id user@mac-pro.local
```

Enter the password when prompted. This is the **last time** you'll need it!

### Step 2.4: Test Passwordless SSH

```bash
ssh user@mac-pro.local hostname
```

**Expected output:** `mac-pro.local` (no password prompt)

If this works, SSH is configured correctly!

If it asks for a password, see troubleshooting below.

## Part 3: Cluster Configuration

### Step 3.1: Create Hostfile

**On controller node:**

```bash
cp hosts.txt.template hosts.txt
nano hosts.txt
```

Edit with your actual hostnames:

```
mac-studio.local slots=8
mac-pro.local slots=12
```

**Tip:** Set `slots=` to the number of CPU cores you want to use.

Check your CPU count with:
```bash
sysctl -n hw.ncpu
```

### Step 3.2: Verify MPI

**Test on controller only:**

```bash
mpirun -np 4 hostname
```

**Expected output:**
```
mac-studio.local
mac-studio.local
mac-studio.local
mac-studio.local
```

**Test across cluster:**

```bash
mpirun --hostfile hosts.txt -np 4 hostname
```

**Expected output:**
```
mac-studio.local
mac-studio.local
mac-pro.local
mac-pro.local
```

If you see both hostnames, MPI is working across nodes!

## Part 4: GPU Setup (Optional)

### Step 4.1: Compile Metal Kernels

**On BOTH nodes:**

```bash
chmod +x compile_metal.sh
./compile_metal.sh
```

**Expected output:** Metal kernels compiled successfully!

### Step 4.2: Test GPU

```bash
python3 metal_compute.py
```

You should see your available GPUs listed.

### Step 4.3: Test MPI + GPU

```bash
mpirun --hostfile hosts.txt -np 4 python3 examples/mpi_gpu.py
```

**Expected output:**
```
Rank 0 on mac-studio.local using GPU 0
Rank 1 on mac-studio.local using GPU 1
Rank 2 on mac-pro.local using GPU 0
Rank 3 on mac-pro.local using GPU 1
Total sum across 4 ranks: ...
```

## Part 5: Job Queue Setup

### Step 5.1: Start Job Runner

**On controller node:**

```bash
nohup python3 job_manager.py run > job_runner.log 2>&1 &
```

Check it's running:

```bash
ps aux | grep job_manager
```

### Step 5.2: Submit Test Job

```bash
python3 job_manager.py submit "mpirun --hostfile hosts.txt -np 4 python3 examples/hello_mpi.py"
```

**Expected output:** Job submitted: `<job_id>`

### Step 5.3: Check Job Status

```bash
# List all jobs
python3 job_manager.py list

# Check specific job
python3 job_manager.py info <job_id>
```

### Step 5.4: View Job Output

```bash
cat jobs/finished/<job_id>.out
```

## Part 6: Validation Tests

Run these to ensure everything works:

### Test 1: Basic MPI
```bash
mpirun --hostfile hosts.txt -np 8 hostname
```
Should show all cluster nodes

### Test 2: Python MPI
```bash
mpirun --hostfile hosts.txt -np 8 python3 examples/hello_mpi.py
```
Should print hello from all ranks

### Test 3: GPU Compute
```bash
python3 metal_compute.py
```
Should list GPUs and pass test

### Test 4: MPI + GPU
```bash
mpirun --hostfile hosts.txt -np 4 python3 examples/mpi_gpu.py
```
Should show distributed GPU computation

### Test 5: Job Queue
```bash
python3 job_manager.py submit "echo 'Hello from job queue'"
sleep 5
python3 job_manager.py list
```
Job should show as 'finished'

## Troubleshooting

### SSH Key Issues

**Problem:** Still asked for password

**Solution:**
```bash
# Check SSH key permissions
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519

# Add key to SSH agent
ssh-add ~/.ssh/id_ed25519

# Try copying key again
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@mac-pro.local
```

### Hostname Not Resolving

**Problem:** `ssh: Could not resolve hostname`

**Solution 1** - Use IP addresses in `hosts.txt`:
```bash
# Find IP address
ifconfig | grep "inet "

# Use in hosts.txt
192.168.1.100 slots=8
192.168.1.101 slots=12
```

**Solution 2** - Add to `/etc/hosts`:
```bash
sudo nano /etc/hosts

# Add lines:
192.168.1.100  mac-studio.local
192.168.1.101  mac-pro.local
```

### MPI Hangs or Times Out

**Problem:** MPI command hangs indefinitely

**Solution:** Add macOS-specific flags:
```bash
mpirun \
  --mca btl tcp,self \
  --mca pml ob1 \
  --hostfile hosts.txt \
  -np 4 \
  python3 script.py
```

### Metal Compilation Fails

**Problem:** `xcrun: error: unable to find utility "metal"`

**Solution:** Install Xcode Command Line Tools:
```bash
xcode-select --install
```

### Job Runner Not Processing

**Problem:** Jobs stay in 'queued' state

**Solution:**
```bash
# Check if runner is active
ps aux | grep job_manager

# Restart job runner
pkill -f job_manager.py
nohup python3 job_manager.py run > job_runner.log 2>&1 &

# Check logs
tail -f job_runner.log
```

## Next Steps

Now that your cluster is running:

1. **Disable sleep** on compute nodes:
   ```bash
   sudo pmset -a disablesleep 1
   ```

2. **Create your first real job:**
   ```bash
   # Edit and save your MPI program
   nano my_computation.py
   
   # Submit to queue
   python3 job_manager.py submit "mpirun --hostfile hosts.txt -np 8 python3 my_computation.py"
   ```

3. **Monitor cluster:**
   ```bash
   # Watch job queue
   watch -n 1 'python3 job_manager.py list'
   
   # Monitor system resources
   htop
   ```

4. **Scale up:** Add more compute nodes by repeating Part 2 for each new machine

## Performance Optimization

### Network
- Use wired Ethernet (10GbE preferred)
- Disable WiFi on compute nodes if using Ethernet

### Storage
- Use NFS or shared storage for large datasets
- Keep temporary files on local SSD

### CPU
- Match CPU architecture across nodes
- Use `--bind-to core` for CPU-intensive workloads

### GPU
- One MPI rank per GPU for maximum throughput
- Monitor GPU usage: `sudo powermetrics --samplers gpu_power`

---

**Congratulations! Your macOS HPC cluster is now ready for production use.**

For more advanced configurations and examples, see the main [README.md](README.md).