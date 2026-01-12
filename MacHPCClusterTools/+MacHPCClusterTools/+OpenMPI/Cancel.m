function Cancel(sshClient, jobId, remoteBase)
    % Cancel a running OpenMPI job
    % 
    % Parameters:
    %   sshClient  - SSH client object
    %   jobId      - Job ID to cancel
    %   remoteBase - Remote base directory (default: '/home')

    if nargin < 2 || isempty(jobId)
        error('JobId required');
    end

    if nargin < 3
        remoteBase = '/home';
    end

    remoteProj = sprintf('%s/hpc_jobs', remoteBase);
    remoteLauncher = sprintf('%s/launch_%s.sh', remoteProj, jobId);

    % Find process ID
    [status, out] = sshClient.exec(sprintf('pgrep -f %s || echo "NOTFOUND"', remoteLauncher));

    if contains(out, 'NOTFOUND') || isempty(strtrim(out))
        warning('Job %s is not running or already completed', jobId);
        return;
    end

    pid = strtrim(out);

    % Kill the process (SIGTERM first, then SIGKILL if needed)
    fprintf('Cancelling job %s (PID: %s)...\n', jobId, pid);
    [status1, ~] = sshClient.exec(sprintf('kill %s', pid));

    % Wait a moment
    pause(2);

    % Check if still running
    [~, checkOut] = sshClient.exec(sprintf('ps -p %s || echo "GONE"', pid));

    if ~contains(checkOut, 'GONE')
        % Force kill
        fprintf('Force killing job %s...\n', jobId);
        [status2, ~] = sshClient.exec(sprintf('kill -9 %s', pid));
        
        if status2 ~= 0
            error('Failed to force kill job %s', jobId);
        end
    end

    % Mark job as cancelled in output
    remoteOut = sprintf('%s/%s.out', remoteProj, jobId);
    sshClient.exec(sprintf('echo "\n[CANCELLED at $(date)]" >> %s || true', remoteOut));

    fprintf('Job %s cancelled successfully\n', jobId);
end