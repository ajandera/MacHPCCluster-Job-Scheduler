"""
Simple MPI Hello World Example
Tests multi-node communication
"""

from mpi4py import MPI
import socket

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()
hostname = socket.gethostname()

print(f"Hello from rank {rank}/{size} on {hostname}")

# Barrier to synchronize output
comm.Barrier()

if rank == 0:
    print(f"\n✅ MPI working with {size} processes across cluster")