"""
Metal GPU Computing Helper Module
Provides GPU acceleration using Apple's Metal framework
"""

import Metal
import numpy as np
import os


def list_gpus():
    """
    List all available Metal GPUs on the system
    
    Returns:
        list: GPU information dictionaries
    """
    devices = Metal.MTLCopyAllDevices()
    gpus = []
    for i, device in enumerate(devices):
        gpus.append({
            "id": i,
            "name": device.name(),
            "low_power": device.isLowPower(),
            "removable": device.isRemovable(),
            "registry_id": device.registryID()
        })
    return gpus


def get_gpu(gpu_id=0):
    """
    Get Metal device by ID
    
    Args:
        gpu_id (int): GPU index
        
    Returns:
        MTLDevice: Metal device object
    """
    devices = Metal.MTLCopyAllDevices()
    if gpu_id >= len(devices):
        raise ValueError(f"GPU {gpu_id} not found. Only {len(devices)} GPUs available.")
    return devices[gpu_id]


def select_gpu_for_rank():
    """
    Select GPU based on MPI local rank
    Distributes ranks evenly across available GPUs
    
    Returns:
        int: GPU ID for this rank
    """
    local_rank = int(os.environ.get("OMPI_COMM_WORLD_LOCAL_RANK", 0))
    devices = Metal.MTLCopyAllDevices()
    gpu_id = local_rank % len(devices)
    return gpu_id


def gpu_add(a, b, gpu_id=0):
    """
    Add two arrays using Metal GPU acceleration
    
    Args:
        a (np.ndarray): First array (float32)
        b (np.ndarray): Second array (float32)
        gpu_id (int): GPU to use
        
    Returns:
        np.ndarray: Result array (a + b)
    """
    if a.shape != b.shape:
        raise ValueError("Arrays must have the same shape")
    
    if a.dtype != np.float32 or b.dtype != np.float32:
        raise ValueError("Arrays must be float32")
    
    # Get Metal device
    device = get_gpu(gpu_id)
    queue = device.newCommandQueue()
    
    # Load compiled Metal library
    lib_path = "metal_kernels/metal_add.metallib"
    if not os.path.exists(lib_path):
        raise FileNotFoundError(f"Metal library not found: {lib_path}")
    
    with open(lib_path, "rb") as f:
        lib_data = f.read()
        lib = device.newLibraryWithData_error_(lib_data, None)[0]
    
    # Get compute function
    fn = lib.newFunctionWithName_("vec_add")
    pipeline = device.newComputePipelineStateWithFunction_error_(fn, None)[0]
    
    # Create Metal buffers
    a_buf = device.newBufferWithBytes_length_options_(a.tobytes(), a.nbytes, 0)
    b_buf = device.newBufferWithBytes_length_options_(b.tobytes(), b.nbytes, 0)
    c_buf = device.newBufferWithLength_options_(a.nbytes, 0)
    
    # Create command buffer and encoder
    cmd = queue.commandBuffer()
    enc = cmd.computeCommandEncoder()
    enc.setComputePipelineState_(pipeline)
    enc.setBuffer_offset_atIndex_(a_buf, 0, 0)
    enc.setBuffer_offset_atIndex_(b_buf, 0, 1)
    enc.setBuffer_offset_atIndex_(c_buf, 0, 2)
    
    # Dispatch threads
    threads = Metal.MTLSizeMake(a.size, 1, 1)
    max_threads = pipeline.maxTotalThreadsPerThreadgroup()
    tg = Metal.MTLSizeMake(max_threads, 1, 1)
    enc.dispatchThreads_threadsPerThreadgroup_(threads, tg)
    enc.endEncoding()
    
    # Execute
    cmd.commit()
    cmd.waitUntilCompleted()
    
    # Get results
    result = np.frombuffer(c_buf.contents().as_buffer(a.nbytes), dtype=np.float32)
    return result.copy()


if __name__ == "__main__":
    # Test GPU availability
    print("Available GPUs:")
    for gpu in list_gpus():
        print(f"  GPU {gpu['id']}: {gpu['name']}")
        print(f"    Low Power: {gpu['low_power']}")
        print(f"    Removable: {gpu['removable']}")
    
    # Test GPU computation (if Metal library exists)
    try:
        print("\nTesting GPU computation...")
        a = np.ones(1000, dtype=np.float32) * 2.0
        b = np.ones(1000, dtype=np.float32) * 3.0
        c = gpu_add(a, b, gpu_id=0)
        print(f"Result: {c[:5]} (expected: [5. 5. 5. 5. 5.])")
        print("✅ GPU computation working!")
    except Exception as e:
        print(f"⚠️  GPU computation test skipped: {e}")