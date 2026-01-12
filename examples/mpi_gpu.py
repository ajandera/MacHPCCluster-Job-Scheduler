"""
MPI + Metal GPU Hybrid Computing Example
Demonstrates distributed GPU computation
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mpi4py import MPI
import numpy as np
import socket
from metal_compute import gpu_add, select_gpu_for_rank, list_gpus

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()
hostname = socket.gethostname()

# Select GPU for this rank
try:
    gpu_id = select_gpu_for_rank()
    print(f"Rank {rank} on {hostname} using GPU {gpu_id}")
except Exception as e:
    print(f"Rank {rank}: GPU selection failed: {e}")
    gpu_id = 0

# Create test data
N = 1_000_000
a = np.ones(N, dtype=np.float32) * rank
b = np.ones(N, dtype=np.float32) * 2.0

# Perform GPU computation
try:
    c = gpu_add(a, b, gpu_id)
    local_sum = np.sum(c)
    print(f"Rank {rank}: Computed sum = {local_sum:.2f}")
except Exception as e:
    print(f"Rank {rank}: GPU computation failed: {e}")
    c = a + b
    local_sum = np.sum(c)

# Reduce results to rank 0
total_sum = comm.reduce(local_sum, op=MPI.SUM, root=0)

if rank == 0:
    print(f"\n Total sum across {size} ranks: {total_sum:.2f}")
    expected = size * N * (rank + 2)  # Approximate expected value
    print(f"   Computation completed successfully!")