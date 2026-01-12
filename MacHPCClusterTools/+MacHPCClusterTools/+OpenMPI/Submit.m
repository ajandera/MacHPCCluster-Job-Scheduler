function jobId = Submit(sshClient, sharedPath, scriptPath, varargin)
    % Submit a MATLAB script to OpenMPI cluster
    % 
    % Parameters:
    %   sshClient  - SSH client object
    %   sharedPath - Shared storage path (e.g., '/srv/hpc/shared')
    %   scriptPath - Local path to MATLAB script
    %   varargin   - Name-value pairs:
    %                'numProcs', 4       - Number of MPI processes
    %                'hostsFile', 'hosts.txt' - Path to MPI hosts file
    %                'remoteBase', '/home'    - Remote base directory
    %                'useGPU', false          - Enable GPU support
    %                'args', ''               - Arguments to pass to script

    p = inputParser();
    addParameter(p, 'numProcs', 4);
    addParameter(p, 'hostsFile', 'hosts.txt');
    addParameter(p, 'remoteBase', '/home');
    addParameter(p, 'useGPU', false);
    addParameter(p, 'args', '');
    parse(p, varargin{:});
    pr = p.Results;

    [~, name, ext] = fileparts(scriptPath);
    timestamp = num2str(floor(posixtime(datetime('now'))));
    jobId = sprintf('%s_%s', name, timestamp);
    remoteProj = sprintf('%s/hpc_jobs', pr.remoteBase);

    % Ensure remote directory
    sshClient.exec(sprintf('mkdir -p %s', remoteProj));

    % Upload script
    remotePath = sprintf('%s/%s%s', remoteProj, name, ext);
    MacHPCClusterTools.SSH.SCP.put(sshClient, scriptPath, remotePath);

    % Upload hosts file if it exists locally
    localHostsFile = pr.hostsFile;
    remoteHostsFile = sprintf('%s/hosts.txt', remoteProj);
    if exist(localHostsFile, 'file')
        MacHPCClusterTools.SSH.SCP.put(sshClient, localHostsFile, remoteHostsFile);
    else
        warning('Hosts file %s not found locally, assuming it exists on remote', localHostsFile);
    end

    % Prepare output files
    remoteOut = sprintf('%s/%s.out', remoteProj, jobId);
    remoteErr = sprintf('%s/%s.err', remoteProj, jobId);

    % Build MATLAB run command
    if ~isempty(pr.args)
        runCmd = sprintf('run(''%s''); %s', name, pr.args);
    else
        runCmd = sprintf('run(''%s'');', name);
    end

    % Build shared path export
    sharedExport = '';
    if ~isempty(sharedPath)
        sharedExport = sprintf('export HPC_SHARED_PATH=%s\n', sharedPath);
    end

    % Build MPI flags for macOS
    mpiFlags = '--mca btl tcp,self --mca pml ob1';

    % Build launcher script
    launcher = sprintf(['#!/bin/bash\n' ...
        '# OpenMPI Job Launcher\n' ...
        '# Job: %s\n' ...
        '# Submitted: %s\n\n' ...
        '%s' ...
        'cd %s\n\n' ...
        'mpirun %s \\\n' ...
        '  --hostfile %s \\\n' ...
        '  -np %d \\\n' ...
        '  matlab -nodisplay -r "try, %s; catch e, disp(getReport(e)); exit(1); end; exit(0)" \\\n' ...
        '  > %s 2> %s\n\n' ...
        'echo "Job %s completed at $(date)" >> %s\n'], ...
        jobId, datestr(now), sharedExport, remoteProj, mpiFlags, ...
        remoteHostsFile, pr.numProcs, runCmd, remoteOut, remoteErr, jobId, remoteOut);

    % Write launcher to temp file
    tmp = [tempname '.sh'];
    fid = fopen(tmp, 'w');
    fwrite(fid, launcher);
    fclose(fid);

    % Upload launcher
    remoteLauncher = sprintf('%s/launch_%s.sh', remoteProj, jobId);
    MacHPCClusterTools.SSH.SCP.put(sshClient, tmp, remoteLauncher);
    delete(tmp);

    % Make launcher executable
    sshClient.exec(sprintf('chmod +x %s', remoteLauncher));

    % Submit job (run in background with nohup)
    submitCmd = sprintf('cd %s && nohup %s > /dev/null 2>&1 & echo $!', ...
        remoteProj, remoteLauncher);
    [status, out] = sshClient.exec(submitCmd);

    if status ~= 0
        error('Job submission failed: %s', out);
    end

    pid = strtrim(out);
    fprintf('Job submitted: %s (PID: %s)\n', jobId, pid);

    % Store job info in shared storage if available
    if ~isempty(sharedPath)
        jobInfoCmd = sprintf('echo "%s|%s|%s|RUNNING" >> %s/jobs.log', ...
            jobId, pid, datestr(now), sharedPath);
        sshClient.exec(jobInfoCmd);
    end
end