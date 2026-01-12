function s = Status(sshClient, jobId, remoteBase)
    % Check status of an OpenMPI job
    % 
    % Parameters:
    %   sshClient  - SSH client object
    %   jobId      - Job ID (e.g., 'myscript_1234567890')
    %   remoteBase - Remote base directory (default: '/home')

    if nargin < 2 || isempty(jobId)
        error('JobId required');
    end

    if nargin < 3
        remoteBase = '/home';
    end

    remoteProj = sprintf('%s/hpc_jobs', remoteBase);
    remoteLauncher = sprintf('%s/launch_%s.sh', remoteProj, jobId);

    % Check if launcher process is still running
    [status, out] = sshClient.exec(sprintf('pgrep -f %s || echo "NOTFOUND"', remoteLauncher));

    if contains(out, 'NOTFOUND') || isempty(strtrim(out))
        % Process not running - check if output files exist
        remoteOut = sprintf('%s/%s.out', remoteProj, jobId);
        [status2, ~] = sshClient.exec(sprintf('test -f %s && echo "EXISTS"', remoteOut));
        
        if status2 == 0
            s = 'COMPLETED';
        else
            s = 'UNKNOWN';
        end
    else
        % Process is running
        pid = strtrim(out);
        
        % Get more info about the process
        [~, psOut] = sshClient.exec(sprintf('ps -p %s -o etime,%%cpu,%%mem || true', pid));
        
        if ~isempty(strtrim(psOut))
            lines = strsplit(strtrim(psOut), '\n');
            if numel(lines) > 1
                info = strtrim(lines{2});
                s = sprintf('RUNNING (PID: %s, %s)', pid, info);
            else
                s = sprintf('RUNNING (PID: %s)', pid);
            end
        else
            s = sprintf('RUNNING (PID: %s)', pid);
        end
    end

    fprintf('Job %s: %s\n', jobId, s);
end