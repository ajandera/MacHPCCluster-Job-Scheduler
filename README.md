# MacHPCCluster Job Scheduler

> **Local Apple Silicon / Intel Mac HPC Cluster for MATLAB Workloads with SLURM**
> Train neural networks, run evolutionary algorithms, and parallelize MATLAB workloads without MATLAB Parallel Server licensing.

---

## Overview

MacHPCClusterTools enables you to:

| Feature                                          | Supported |
| ------------------------------------------------ | :-------: |
| Submit `.m` files to a SLURM-managed Mac cluster |     ✔     |
| GPU-aware job scheduling (Metal Compute)         |     ✔     |
| SSH agent integration + passphrase GUI           |     ✔     |
| Auto node discovery (Bonjour)                    |     ✔     |
| Unified project & results syncing                |     ✔     |
| Job history & monitoring dashboard               |     ✔     |
| No MATLAB Parallel Server required               |     ✔     |

Runs on macOS 12+ (Intel or Apple Silicon) with **up to 3 nodes tested**:
**2× Mac Pro + 1× Mac Studio** recommended.

---

## Architecture

```
MATLAB App (GUI)
   ⬇ SSH + SCP + rsync
Mac Pro (Master)  — SLURM Controller (slurmctld)
   ⬇ Cluster Network
Mac Pro (Worker)  — SLURM Compute Node (slurmd)
   ⬇
Mac Studio (Worker)
```

Shared storage synced automatically:

```
~/mac-hpc/projects   → Code upload
~/mac-hpc/results    → Output download
~/mac-hpc/scratch    → Temporary data
```

---

## Installation

### 1. On MATLAB Workstation (Your main Mac)

1. Download and unzip toolbox folder
2. In MATLAB Command Window:

```matlab
cd MacHPCClusterTools
install
app = MacHPCClusterToolsApp();
```

You can then launch the GUI from:
➡ *MATLAB Apps* → **Mac HPC Cluster Tools**

---

### 2. On each Cluster Node (Mac Pro / Mac Studio)

Run the provided setup script:

```bash
bash setup_hpc_node.sh
```

This installs:

| Component               | Purpose                      |
| ----------------------- | ---------------------------- |
| Homebrew                | Package manager              |
| SLURM                   | Job scheduler                |
| SSH + rsync             | Remote access & sync         |
| GPU tools               | Metal compute support        |
| Default cluster folders | Scratch + Projects + Results |

Reboot recommended afterwards.

---

## App GUI Features

### Setup Wizard (first launch)

✔ Add cluster nodes over SSH
✔ Configure paths and credentials
✔ Connection test & save profile

### Job Manager

| Tab     | Function                                    |
| ------- | ------------------------------------------- |
| Submit  | Pick `.m` script, CPUs, GPU, memory, time   |
| Queue   | View **Pending / Running / Completed** jobs |
| Logs    | Inspect `.out` and `.err` directly          |
| Results | Download automatically & view in MATLAB     |
| Nodes   | FLOPS + GPU detection, load monitoring      |

---

## Submitting Jobs

Running a script on the cluster:

```matlab
job = MacHPC.submit('trainModel.m', ...
    CPUs=8, UseGPU=true, Time="01:30:00", Memory="32G");
```

Retrieve output:

```matlab
MacHPC.fetch(job)
```

Check status:

```matlab
MacHPC.status(job)
```

Cancel if needed:

```matlab
MacHPC.cancel(job)
```

---

## SSH Integration

✔ Passphrase-protected private keys
✔ SSH agent auto-start
✔ Automatic known_hosts provisioning
✔ Per-node credential storage (secure)

Supports:

* Public key authentication (recommended)
* Optional password fallback (visual prompt)

---

## GPU & FLOPS Detection

Each node reports:

* CPU cores
* Memory capacity
* GPU model + Metal performance score
* Live FLOPS benchmark (startup option)

Available in GUI under **Nodes** tab.

---

## Shared Data & MATLAB Integration

| Folder                | Role                           |
| --------------------- | ------------------------------ |
| `~/mac-hpc/projects/` | Scripts uploaded to nodes      |
| `~/mac-hpc/results/`  | Receives `.mat` and data files |
| `~/mac-hpc/scratch/`  | Temporary compute area         |

`scp` + `rsync` ensures minimal data transfer overhead.

---

## Advanced SLURM Configuration

Config file location:

```
/opt/slurm/slurm.conf
```

Multi-node example:

```
ClusterName=MacCluster
SlurmctldHost=MacProMaster

NodeName=MacProMaster CPUs=32 RealMemory=65536 State=UNKNOWN
NodeName=MacProWorker CPUs=32 RealMemory=65536 State=UNKNOWN
NodeName=MacStudioWorker CPUs=24 RealMemory=98304 Gres=gpu:1 State=UNKNOWN

PartitionName=default Nodes=ALL Default=YES MaxTime=INFINITE State=UP
```

Deploy:

```bash
slurmctld
slurmd
sinfo
```

---

## Compare with MATLAB Parallel Server?

| Requirement               | MATLAB Parallel Server | MacHPCClusterTools |
| ------------------------- | ---------------------- | ------------------ |
| macOS cluster support     | ❌                      | ✔                  |
| License needed per worker | ✔                      | ❌                  |
| SLURM integration         | ✔                      | ✔                  |
| GPU jobs on macOS         | ✔                      | ✔                  |
| Peer-to-peer Mac cluster  | ❌                      | ✔                  |

---

## Requirements

| Component        | Minimum             |
| ---------------- | ------------------- |
| macOS            | 12+                 |
| MATLAB           | R2022b+ recommended |
| SSH connectivity | Required            |
| Node count       | 1–8 validated       |

---

## Troubleshooting

Jobs remain in **PENDING**

```
squeue -u $USER
sinfo
slurmd -Dvvv
```

Cannot SSH to node
→ Ensure **Remote Login** enabled in System Settings
→ Verify keys in `~/.ssh/authorized_keys`

GPU not detected
→ Install latest macOS + driver firmware
→ Only supported on **Apple Silicon** or **MPX GPU** equipped Mac Pro

---

## Credits

Developed by Aleš Jandera (ales.jandera@tuke.sk)
2025 © MacHPCClusterTools
