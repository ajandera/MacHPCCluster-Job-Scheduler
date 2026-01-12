function Logs(sshClient, sharedPath, jobId, dest, remoteBase)
    % Fetch output logs for an OpenMPI job
    % 
    % Parameters:
    %   sshClient  - SSH client object
    %   sharedPath - Shared storage path
    %   jobId      - Job ID
    %   dest       - Local destination directory (default: current directory)
    %   remoteBase - Remote base directory (default: '/home')

    if nargin < 4
        dest = pwd;
    end

    if nargin < 5
        remoteBase = '/home';
    end

    remoteProj = sprintf('%s/hpc_jobs', remoteBase);
    fetched = false;

    % Try to fetch job output files
    remoteOut = sprintf('%s/%s.out', remoteProj, jobId);
    remoteErr = sprintf('%s/%s.err', remoteProj, jobId);

    [status, ~] = sshClient.exec(sprintf('test -f %s && echo "EXISTS"', remoteOut));
    if status == 0
        localOut = fullfile(dest, sprintf('%s.out', jobId));
        try
            MacHPCClusterTools.SSH.SCP.get(sshClient, remoteOut, localOut);
            fprintf('Downloaded: %s\n', localOut);
            fetched = true;
        catch ME
            warning('Failed to fetch %s: %s', remoteOut, ME.message);
        end
    end

    [status, ~] = sshClient.exec(sprintf('test -f %s && echo "EXISTS"', remoteErr));
    if status == 0
        localErr = fullfile(dest, sprintf('%s.err', jobId));
        try
            MacHPCClusterTools.SSH.SCP.get(sshClient, remoteErr, localErr);
            fprintf('Downloaded: %s\n', localErr);
            fetched = true;
        catch ME
            warning('Failed to fetch %s: %s', remoteErr, ME.message);
        end
    end

    % Try to fetch launcher script for reference
    remoteLauncher = sprintf('%s/launch_%s.sh', remoteProj, jobId);
    [status, ~] = sshClient.exec(sprintf('test -f %s && echo "EXISTS"', remoteLauncher));
    if status == 0
        localLauncher = fullfile(dest, sprintf('launch_%s.sh', jobId));
        try
            MacHPCClusterTools.SSH.SCP.get(sshClient, remoteLauncher, localLauncher);
            fprintf('Downloaded: %s\n', localLauncher);
        catch ME
            warning('Failed to fetch launcher: %s', ME.message);
        end
    end

    % Try shared outputs if configured
    if ~isempty(sharedPath)
        [status, out2] = sshClient.exec(sprintf('ls %s/outputs 2>/dev/null | grep %s || true', sharedPath, jobId));
        if status == 0 && ~isempty(strtrim(out2))
            items = strsplit(strtrim(out2), newline);
            for i = 1:numel(items)
                fn = strtrim(items{i});
                if isempty(fn)
                    continue;
                end
                remoteFile = sprintf('%s/outputs/%s', sharedPath, fn);
                localFile = fullfile(dest, fn);
                try
                    MacHPCClusterTools.SSH.SCP.get(sshClient, remoteFile, localFile);
                    fprintf('Downloaded from shared: %s\n', localFile);
                    fetched = true;
                catch ME
                    warning('Failed to fetch shared file %s: %s', remoteFile, ME.message);
                end
            end
        end
    end

    % Try shared logs directory
    if ~isempty(sharedPath)
        [status, out3] = sshClient.exec(sprintf('ls %s/logs 2>/dev/null | grep %s || true', sharedPath, jobId));
        if status == 0 && ~isempty(strtrim(out3))
            items = strsplit(strtrim(out3), newline);
            for i = 1:numel(items)
                fn = strtrim(items{i});
                if isempty(fn)
                    continue;
                end
                remoteFile = sprintf('%s/logs/%s', sharedPath, fn);
                localFile = fullfile(dest, fn);
                try
                    MacHPCClusterTools.SSH.SCP.get(sshClient, remoteFile, localFile);
                    fprintf('Downloaded from shared logs: %s\n', localFile);
                    fetched = true;
                catch ME
                    warning('Failed to fetch log file %s: %s', remoteFile, ME.message);
                end
            end
        end
    end

    if ~fetched
        warning('No output files found for job %s', jobId);
    else
        fprintf('All available logs fetched to: %s\n', dest);
    end
end