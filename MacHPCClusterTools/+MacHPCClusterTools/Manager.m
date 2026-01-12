classdef Manager < handle
    % Manager - main entry point for MacHPCClusterTools (OpenMPI version)
    % 
    % Example usage:
    %   mgr = MacHPCClusterTools.Manager('mac-pro.local', 'myuser', '~/.ssh/id_ed25519');
    %   mgr.connect();
    %   jobId = mgr.submit('myscript.m', 'numProcs', 8, 'hostsFile', 'hosts.txt');
    %   mgr.status(jobId);
    %   mgr.fetch(jobId);
    %   mgr.cancel(jobId);
    %   mgr.disconnect();
    
    properties
        SSH              % SSH client object (MacHPCClusterTools.SSH.Client)
        SharedStorage    % Shared storage path (e.g., '/srv/hpc/shared')
        Host char = ''   % Controller hostname
        User char = ''   % SSH username
        Key char = ''    % SSH key path
        Port = 22        % SSH port
        RemoteBase char = '/home'  % Remote base directory
        HostsFile char = 'hosts.txt'  % MPI hosts file
    end

    methods
        function obj = Manager(host, user, key, port)
            % Create a new cluster manager
            if nargin >= 1
                obj.Host = host;
            end
            if nargin >= 2
                obj.User = user;
            end
            if nargin >= 3
                obj.Key = key;
            end
            if nargin >= 4
                obj.Port = port;
            end
            
            % Set default shared storage
            obj.SharedStorage = '/srv/hpc/shared';
        end

        function connect(obj)
            % Create SSH client and connect to controller node
            obj.SSH = MacHPCClusterTools.SSH.Client(obj.Host, obj.User, obj.Key, obj.Port);
            obj.SSH.connect();
            fprintf('[Manager] Connected to %s@%s:%d\n', obj.User, obj.Host, obj.Port);
            
            % Check if OpenMPI is available
            [status, out] = obj.SSH.exec('which mpirun');
            if status == 0
                fprintf('[Manager] OpenMPI found: %s\n', strtrim(out));
            else
                warning('OpenMPI not found on remote system. Install with: brew install open-mpi');
            end
        end

        function disconnect(obj)
            % Disconnect from cluster
            if ~isempty(obj.SSH)
                obj.SSH.close();
                obj.SSH = [];
            end
            fprintf('[Manager] Disconnected.\n');
        end

        function jobId = submit(obj, scriptPath, varargin)
            % Submit a MATLAB script to the OpenMPI cluster
            %
            % Parameters (name-value pairs):
            %   'numProcs'   - Number of MPI processes (default: 4)
            %   'hostsFile'  - Path to hosts file (default: obj.HostsFile)
            %   'remoteBase' - Remote base directory (default: obj.RemoteBase)
            %   'useGPU'     - Enable GPU support (default: false)
            %   'args'       - Arguments to pass to script (default: '')
            
            if isempty(obj.SSH)
                error('Not connected. Call connect() first.');
            end
            
            % Parse optional arguments
            p = inputParser();
            addParameter(p, 'numProcs', 4);
            addParameter(p, 'hostsFile', obj.HostsFile);
            addParameter(p, 'remoteBase', obj.RemoteBase);
            addParameter(p, 'useGPU', false);
            addParameter(p, 'args', '');
            parse(p, varargin{:});
            
            jobId = MacHPCClusterTools.OpenMPI.Submit(obj.SSH, obj.SharedStorage, ...
                scriptPath, 'numProcs', p.Results.numProcs, ...
                'hostsFile', p.Results.hostsFile, ...
                'remoteBase', p.Results.remoteBase, ...
                'useGPU', p.Results.useGPU, ...
                'args', p.Results.args);
        end

        function s = status(obj, jobId)
            % Check status of a submitted job
            if isempty(obj.SSH)
                error('Not connected. Call connect() first.');
            end
            s = MacHPCClusterTools.OpenMPI.Status(obj.SSH, jobId, obj.RemoteBase);
        end

        function fetch(obj, jobId, dest)
            % Fetch logs and outputs for a job
            if nargin < 3
                dest = pwd;
            end
            if isempty(obj.SSH)
                error('Not connected. Call connect() first.');
            end
            MacHPCClusterTools.OpenMPI.Logs(obj.SSH, obj.SharedStorage, jobId, dest, obj.RemoteBase);
        end

        function cancel(obj, jobId)
            % Cancel a running job
            if isempty(obj.SSH)
                error('Not connected. Call connect() first.');
            end
            MacHPCClusterTools.OpenMPI.Cancel(obj.SSH, jobId, obj.RemoteBase);
        end

        function hosts = discoverNodes(obj, timeout)
            % Discover SSH-accessible nodes on the network
            if nargin < 2
                timeout = 4;
            end
            hosts = MacHPCClusterTools.Network.discoverSSHHosts(timeout);
        end
        
        function nodes = listNodes(obj)
            % List nodes from hosts file and check their status
            if isempty(obj.SSH)
                error('Not connected. Call connect() first.');
            end
            
            remoteHostsFile = sprintf('%s/hpc_jobs/hosts.txt', obj.RemoteBase);
            [status, out] = obj.SSH.exec(sprintf('cat %s 2>/dev/null || echo "NOTFOUND"', remoteHostsFile));
            
            if contains(out, 'NOTFOUND')
                warning('Hosts file not found: %s', remoteHostsFile);
                nodes = struct([]);
                return;
            end
            
            lines = strsplit(strtrim(out), newline);
            nodes = struct('hostname', {}, 'slots', {}, 'status', {});
            
            for i = 1:numel(lines)
                line = strtrim(lines{i});
                if isempty(line) || startsWith(line, '#')
                    continue;
                end
                
                parts = strsplit(line);
                hostname = parts{1};
                slots = 1;
                
                for j = 2:numel(parts)
                    if contains(parts{j}, 'slots=')
                        slots = str2double(extractAfter(parts{j}, 'slots='));
                    end
                end
                
                % Check if node is reachable
                [st, ~] = obj.SSH.exec(sprintf('ssh -o ConnectTimeout=3 %s "echo OK" 2>/dev/null', hostname));
                nodeStatus = 'offline';
                if st == 0
                    nodeStatus = 'online';
                end
                
                nodes(end+1) = struct('hostname', hostname, 'slots', slots, 'status', nodeStatus);
            end
            
            % Display results
            fprintf('\nCluster Nodes:\n');
            fprintf('%-30s %-10s %-10s\n', 'Hostname', 'Slots', 'Status');
            fprintf('%s\n', repmat('-', 1, 52));
            for i = 1:numel(nodes)
                fprintf('%-30s %-10d %-10s\n', nodes(i).hostname, nodes(i).slots, nodes(i).status);
            end
        end
        
        function setupSharedStorage(obj)
            % Create shared storage directories on controller
            if isempty(obj.SSH)
                error('Not connected. Call connect() first.');
            end
            
            fprintf('Creating shared storage at %s...\n', obj.SharedStorage);
            obj.SSH.exec(sprintf('mkdir -p %s/{inputs,outputs,logs,tmp} && chmod 2775 %s', ...
                obj.SharedStorage, obj.SharedStorage));
            fprintf('Shared storage created successfully.\n');
            fprintf('Configure NFS to share this directory with compute nodes.\n');
        end
        
        function listJobs(obj, numJobs)
            % List recent jobs from shared storage log
            if nargin < 2
                numJobs = 20;
            end
            
            if isempty(obj.SSH)
                error('Not connected. Call connect() first.');
            end
            
            jobsLog = sprintf('%s/jobs.log', obj.SharedStorage);
            [status, out] = obj.SSH.exec(sprintf('tail -n %d %s 2>/dev/null || echo "NOLOG"', numJobs, jobsLog));
            
            if contains(out, 'NOLOG')
                fprintf('No job history found.\n');
                return;
            end
            
            lines = strsplit(strtrim(out), newline);
            fprintf('\nRecent Jobs:\n');
            fprintf('%-30s %-10s %-20s %-10s\n', 'Job ID', 'PID', 'Submitted', 'Status');
            fprintf('%s\n', repmat('-', 1, 72));
            
            for i = 1:numel(lines)
                line = strtrim(lines{i});
                if isempty(line)
                    continue;
                end
                
                parts = strsplit(line, '|');
                if numel(parts) >= 4
                    fprintf('%-30s %-10s %-20s %-10s\n', parts{1}, parts{2}, parts{3}, parts{4});
                end
            end
        end
    end
end