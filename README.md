# macOS HPC Cluster with OpenMPI

A complete, production-ready High-Performance Computing (HPC) setup for macOS using OpenMPI, Metal GPU acceleration, and a lightweight job queue system.

## 🎯 Features

- ✅ Multi-node MPI cluster using SSH
- ✅ Metal GPU acceleration (Apple Silicon & AMD GPUs)
- ✅ Automatic GPU selection per MPI rank
- ✅ Fault-tolerant job queue (Slurm-like)
- ✅ Cross-node distributed computing
- ✅ Python and C/C++ support

## 📋 Requirements

- **macOS** 10.15 or later (Monterey+ recommended)
- **Multiple Mac computers** connected via network
- **Homebrew** package manager
- **SSH access** between all nodes

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/macos-hpc-cluster.git
cd macos-hpc-cluster
```

### 2. Run Installation Script (on ALL nodes)

```bash
chmod +x install.sh
./install.sh
```

This installs:
- OpenMPI
- Python 3 with mpi4py
- Metal framework bindings
- Creates necessary directories

### 3. Configure SSH Keys

On your **controller node** (e.g., Mac Studio):

```bash
# Generate SSH key if you don't have one
ssh-keygen -t ed25519

# Copy to each compute node
ssh-copy-id user@mac-pro.local
ssh-copy-id user@mac-mini.local

# Test passwordless SSH
ssh user@mac-pro.local hostname
```

✅ You should see the hostname without being prompted for a password.

### 4. Configure Cluster Hosts

Edit `hosts.txt` with your cluster configuration:

```bash
cp hosts.txt.template hosts.txt
nano hosts.txt
```

Example configuration:

```
mac-studio.local slots=8
mac-pro.local slots=12
```

**Important:** Use the same username on all nodes.

### 5. Test MPI Setup

```bash
# Simple hostname test
mpirun --hostfile hosts.txt -np 4 hostname

# Python MPI test
mpirun --hostfile hosts.txt -np 4 python examples/hello_mpi.py
```

Expected output:
```
Hello from rank 0/4 on mac-studio.local
Hello from rank 1/4 on mac-studio.local
Hello from rank 2/4 on mac-pro.local
Hello from rank 3/4 on mac-pro.local
✅ MPI working with 4 processes across cluster
```

### 6. Compile Metal Kernels

```bash
chmod +x compile_metal.sh
./compile_metal.sh
```

### 7. Test GPU + MPI

```bash
mpirun --hostfile hosts.txt -np 4 python examples/mpi_gpu.py
```

## 📚 Usage Guide

### Running MPI Programs

**Basic MPI command:**

```bash
mpirun --hostfile hosts.txt -np 8 ./your_program
```

**With GPU support:**

```bash
mpirun --hostfile hosts.txt -np 4 python your_gpu_script.py
```

**Distribute ranks evenly (2 per node):**

```bash
mpirun --map-by ppr:2:node --hostfile hosts.txt -np 4 python script.py
```

### Job Queue System

The included job manager provides Slurm-like job submission and management.

**Start the job runner (in background):**

```bash
nohup python job_manager.py run > job_runner.log 2>&1 &
```

**Submit a job:**

```bash
python job_manager.py submit "mpirun --hostfile hosts.txt -np 8 python mpi_program.py"
```

**List all jobs:**

```bash
python job_manager.py list
```

**List only running jobs:**

```bash
python job_manager.py list running
```

**Get job details:**

```bash
python job_manager.py info <job_id>
```

**Cancel a job:**

```bash
python job_manager.py cancel <job_id>
```

**View job output:**

```bash
cat jobs/finished/<job_id>.out
cat jobs/finished/<job_id>.err
```

## 🔧 Advanced Configuration

### macOS-Specific MPI Flags

macOS networking can be finicky. Use these flags if you encounter issues:

```bash
mpirun \
  --mca btl tcp,self \
  --mca pml ob1 \
  --hostfile hosts.txt \
  -np 8 \
  ./your_program
```

### GPU Selection

The system automatically assigns GPUs based on MPI local rank:

```python
from metal_compute import select_gpu_for_rank

gpu_id = select_gpu_for_rank()  # Returns 0, 1, 2... based on local rank
```

**Manual GPU selection:**

```python
from metal_compute import gpu_add, list_gpus

# List available GPUs
gpus = list_gpus()
print(gpus)

# Use specific GPU
result = gpu_add(a, b, gpu_id=1)
```

### Custom Metal Kernels

1. Create kernel in `metal_kernels/your_kernel.metal`
2. Compile with:

```bash
cd metal_kernels
xcrun -sdk macosx metal -c your_kernel.metal -o your_kernel.air
xcrun -sdk macosx metallib your_kernel.air -o your_kernel.metallib
```

3. Load in Python using `metal_compute.py` as reference

## 📁 Project Structure

```
macos-hpc-cluster/
├── install.sh              # Installation script
├── compile_metal.sh        # Metal kernel compiler
├── metal_compute.py        # GPU computation module
├── job_manager.py          # Job queue system
├── hosts.txt.template      # Cluster configuration template
├── hosts.txt               # Your cluster configuration (gitignored)
├── metal_kernels/          # Metal GPU kernels
│   ├── metal_add.metal     # Example vector addition
│   └── metal_add.metallib  # Compiled kernel (generated)
├── examples/               # Example programs
│   ├── hello_mpi.py        # Basic MPI test
│   └── mpi_gpu.py          # MPI + GPU example
└── jobs/                   # Job queue data
    ├── queue.json          # Job queue state
    ├── running/            # Running job logs
    └── finished/           # Completed job logs
```

## 🐛 Troubleshooting

### SSH Connection Issues

```bash
# Verify SSH key is added
ssh-add -l

# Test connection manually
ssh -v user@hostname

# Check SSH config
cat ~/.ssh/config
```

### MPI Cannot Find Hosts

```bash
# Verify hostnames resolve
ping mac-pro.local

# Try IP addresses in hosts.txt instead
192.168.1.100 slots=8
```

### Metal Kernel Not Found

```bash
# Recompile Metal kernels
./compile_metal.sh

# Verify metallib exists
ls -l metal_kernels/metal_add.metallib
```

### Permission Denied on Scripts

```bash
# Make scripts executable
chmod +x install.sh compile_metal.sh
```

### Job Runner Not Processing Jobs

```bash
# Check if job runner is running
ps aux | grep job_manager

# View job runner logs
tail -f job_runner.log

# Restart job runner
pkill -f job_manager.py
nohup python job_manager.py run > job_runner.log 2>&1 &
```

## 🎓 Best Practices

### For Production Use

1. **Same OpenMPI version** on all nodes
2. **Same username** across all machines  
3. **Matching Python versions** (use `pyenv` for consistency)
4. **Static IP addresses** or proper DNS
5. **Disable sleep** on compute nodes:
   ```bash
   sudo pmset -a disablesleep 1
   ```
6. **Network optimization:**
   - Use wired Ethernet (not WiFi)
   - 10GbE or higher for large data transfers

### Security Considerations

- Use SSH keys with passphrases
- Restrict SSH access in `/etc/ssh/sshd_config`
- Use firewall rules to limit MPI ports
- Don't expose cluster to public internet

## 📊 Performance Tips

1. **CPU Binding:** Use `--bind-to core` for CPU-intensive tasks
2. **Network Tuning:** Adjust TCP buffer sizes in `sysctl`
3. **GPU Selection:** Assign one rank per GPU for maximum throughput
4. **Data Locality:** Keep data on the node doing computation
5. **Batch Jobs:** Group small jobs together to reduce overhead

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with clear commit messages
4. Test on actual macOS hardware
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- OpenMPI project for cross-platform MPI
- Apple for Metal framework
- mpi4py developers

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/yourusername/macos-hpc-cluster/issues)
- **Discussions:** [GitHub Discussions](https://github.com/yourusername/macos-hpc-cluster/discussions)

## 🔗 Related Resources

- [OpenMPI Documentation](https://www.open-mpi.org/doc/)
- [Metal Programming Guide](https://developer.apple.com/metal/)
- [MPI Tutorial](https://mpitutorial.com/)

---

**Built with ❤️ for the macOS HPC community**