# MacHPCClusterTools - MATLAB Interface (OpenMPI)

MATLAB interface for managing and submitting jobs to your macOS OpenMPI HPC cluster.

## Requirements

- MATLAB R2019b or later
- SSH access to cluster controller
- OpenMPI installed on all cluster nodes
- MacHPCClusterTools package structure:

```
+MacHPCClusterTools/
├── +OpenMPI/
│   ├── Submit.m
│   ├── Status.m
│   ├── Cancel.m
│   └── Logs.m
├── +SSH/
│   ├── Client.m
│   └── +SCP/
│       ├── get.m
│       └── put.m
├── +Network/
│   └── discoverSSHHosts.m
├── Manager.m
└── MacHPCClusterDashboard.m
```

## Quick Start

### 1. Setup Package Structure

Create the package directory structure:

```bash
mkdir -p +MacHPCClusterTools/+OpenMPI
mkdir -p +MacHPCClusterTools/+SSH/+SCP
mkdir -p +MacHPCClusterTools/+Network
```

Place the files:
- `Submit.m`, `Status.m`, `Cancel.m`, `Logs.m` → `+OpenMPI/`
- `Manager.m` → `+MacHPCClusterTools/`
- `MacHPCClusterDashboard.m` → root directory

### 2. Basic Usage (Command Line)

```matlab
% Create manager and connect
mgr = MacHPCClusterTools.Manager('mac-pro.local', 'myuser', '~/.ssh/id_ed25519');
mgr.connect();

% Configure cluster settings
mgr.HostsFile = 'hosts.txt';
mgr.SharedStorage = '/srv/hpc/shared';
mgr.RemoteBase = '/home/myuser';

% Submit a job
jobId = mgr.submit('myscript.m', 'numProcs', 8);

% Check status
mgr.status(jobId);

% Fetch results
mgr.fetch(jobId, './results');

% Cancel job if needed
mgr.cancel(jobId);

% List cluster nodes
mgr.listNodes();

% Disconnect
mgr.disconnect();
```

### 3. GUI Dashboard

Launch the graphical dashboard:

```matlab
MacHPCClusterDashboard
```

Features:
- Connect to cluster
- Discover network nodes
- Submit MATLAB scripts
- Monitor job status
- Fetch job outputs
- List cluster nodes

## Detailed Usage

### Manager Object

The `Manager` class is the main interface:

```matlab
% Constructor
mgr = MacHPCClusterTools.Manager(host, user, keyPath, port)

% Properties
mgr.Host = 'controller.local';     % Controller hostname
mgr.User = 'username';             % SSH username
mgr.Key = '~/.ssh/id_ed25519';    % SSH private key path
mgr.Port = 22;                     % SSH port
mgr.HostsFile = 'hosts.txt';      % MPI hosts file
mgr.SharedStorage = '/srv/hpc/shared';  % Shared storage path
mgr.RemoteBase = '/home/user';    % Remote base directory
```

### Submitting Jobs

```matlab
% Basic submission
jobId = mgr.submit('myscript.m');

% Advanced submission with options
jobId = mgr.submit('myscript.m', ...
    'numProcs', 16, ...           % Number of MPI processes
    'hostsFile', 'hosts.txt', ... % Custom hosts file
    'useGPU', true, ...           % Enable GPU support
    'args', 'param1, param2');    % Script arguments
```

### Job Management

```matlab
% Check job status
status = mgr.status(jobId);
% Returns: 'RUNNING (PID: 12345)', 'COMPLETED', or 'UNKNOWN'

% Fetch job outputs
mgr.fetch(jobId);              % Download to current directory
mgr.fetch(jobId, './results'); % Download to specific directory

% Cancel running job
mgr.cancel(jobId);

% List recent jobs
mgr.listJobs(20);  % Show last 20 jobs
```

### Cluster Management

```matlab
% List cluster nodes
nodes = mgr.listNodes();
% Returns struct array with: hostname, slots, status

% Setup shared storage
mgr.setupSharedStorage();

% Discover network nodes
hosts = mgr.discoverNodes(4);  % 4 second timeout
```

## Example Scripts

### Example 1: Simple Computation

```matlab
% mycomputation.m
function mycomputation()
    % Your computation here
    N = 1e6;
    result = sum(rand(N, 1));
    
    % Save results to shared storage
    sharedPath = getenv('HPC_SHARED_PATH');
    if ~isempty(sharedPath)
        save(fullfile(sharedPath, 'outputs', 'result.mat'), 'result');
    end
    
    fprintf('Computation complete: result = %f\n', result);
end
```

Submit:

```matlab
mgr = MacHPCClusterTools.Manager('cluster.local', 'user', '~/.ssh/id_rsa');
mgr.connect();
jobId = mgr.submit('mycomputation.m', 'numProcs', 4);
```

### Example 2: GPU-Accelerated Job

```matlab
% gpucomputation.m
function gpucomputation()
    % Check if GPU is available
    if gpuDeviceCount > 0
        fprintf('Using GPU: %s\n', gpuDevice().Name);
        A = gpuArray(rand(5000));
        B = gpuArray(rand(5000));
        C = A * B;
        result = gather(sum(C(:)));
    else
        fprintf('No GPU available, using CPU\n');
        A = rand(5000);
        B = rand(5000);
        C = A * B;
        result = sum(C(:));
    end
    
    fprintf('Result: %f\n', result);
end
```

Submit with GPU:

```matlab
jobId = mgr.submit('gpucomputation.m', 'numProcs', 2, 'useGPU', true);
```

### Example 3: Parametric Study

```matlab
% parametric_study.m
function parametric_study(alpha, beta)
    result = alpha^2 + beta^2;
    
    % Save results
    sharedPath = getenv('HPC_SHARED_PATH');
    if ~isempty(sharedPath)
        filename = sprintf('result_a%g_b%g.mat', alpha, beta);
        save(fullfile(sharedPath, 'outputs', filename), 'result', 'alpha', 'beta');
    end
    
    fprintf('alpha=%g, beta=%g, result=%g\n', alpha, beta, result);
end
```

Submit multiple jobs:

```matlab
mgr.connect();

for alpha = 1:5
    for beta = 1:5
        args = sprintf('%d, %d', alpha, beta);
        jobId = mgr.submit('parametric_study.m', ...
                          'numProcs', 1, ...
                          'args', args);
        fprintf('Submitted: alpha=%d, beta=%d, jobId=%s\n', alpha, beta, jobId);
    end
end
```

## 🔧 Configuration

### Hosts File Format

```text
# MPI Hosts Configuration
mac-studio.local slots=8
mac-pro.local slots=12
mac-mini.local slots=4
```

### Environment Variables

Scripts can access these environment variables:

- `HPC_SHARED_PATH` - Path to shared storage (if configured)

Example:

```matlab
sharedPath = getenv('HPC_SHARED_PATH');
if ~isempty(sharedPath)
    outputFile = fullfile(sharedPath, 'outputs', 'myresult.mat');
    save(outputFile, 'data');
end
```

## Troubleshooting

### Connection Issues

```matlab
% Test SSH connection manually
mgr = MacHPCClusterTools.Manager('host', 'user', '~/.ssh/key');
try
    mgr.connect();
    disp('Connection successful');
catch ME
    disp(['Error: ' ME.message]);
end
```

### Job Not Starting

1. Check if OpenMPI is installed:
```matlab
[status, out] = mgr.SSH.exec('which mpirun');
disp(out);
```

2. Verify hosts file exists:
```matlab
[status, out] = mgr.SSH.exec('cat ~/hpc_jobs/hosts.txt');
disp(out);
```

3. Check job status:
```matlab
mgr.status(jobId);
```

### Cannot Fetch Logs

```matlab
% Manually check if output exists
remoteOut = sprintf('/home/user/hpc_jobs/%s.out', jobId);
[status, out] = mgr.SSH.exec(['cat ' remoteOut]);
disp(out);
```

## Performance Tips

1. **Use appropriate number of processes**: Match to available CPU cores
   ```matlab
   jobId = mgr.submit('script.m', 'numProcs', 8);
   ```

2. **Enable GPU for compatible workloads**:
   ```matlab
   jobId = mgr.submit('gpu_script.m', 'useGPU', true);
   ```

3. **Use shared storage for results**:
   ```matlab
   % In your script:
   sharedPath = getenv('HPC_SHARED_PATH');
   save(fullfile(sharedPath, 'outputs', 'result.mat'), 'data');
   ```

4. **Monitor jobs**:
   ```matlab
   % Check status periodically
   while ~contains(mgr.status(jobId), 'COMPLETED')
       pause(10);
   end
   mgr.fetch(jobId);
   ```

## 🔗 Integration with Python Tools

The MATLAB tools work seamlessly with the Python dashboard:

1. Submit from MATLAB:
```matlab
jobId = mgr.submit('script.m', 'numProcs', 4);
```

2. Monitor from Python dashboard
3. Fetch results from either interface

## License

MIT License - See main repository LICENSE file

## Contributing

Submit issues and pull requests to the main repository.

---

**For more information**, see the main repository README and documentation.