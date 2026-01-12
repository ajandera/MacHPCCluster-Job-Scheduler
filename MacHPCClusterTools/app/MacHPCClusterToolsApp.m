function MacHPCClusterDashboard
% OpenMPI HPC Cluster Dashboard for MATLAB
% Simple UIFigure interface for MacHPCClusterTools

% Create main figure
fig = uifigure('Name', 'MacHPCCluster - OpenMPI Dashboard', ...
               'Position', [100 100 900 700]);

% Title
uilabel(fig, 'Position', [20 660 600 30], ...
        'Text', 'MacHPCCluster - OpenMPI Dashboard', ...
        'FontSize', 16, 'FontWeight', 'bold');

% Connection panel
panelConn = uipanel(fig, 'Title', 'Connection', ...
                    'Position', [20 550 860 100]);

uilabel(panelConn, 'Position', [10 50 50 22], 'Text', 'Host:');
txtHost = uieditfield(panelConn, 'text', 'Position', [70 50 150 22], ...
                      'Value', 'mac-pro.local');

uilabel(panelConn, 'Position', [230 50 50 22], 'Text', 'User:');
txtUser = uieditfield(panelConn, 'text', 'Position', [290 50 100 22], ...
                      'Value', getenv('USER'));

uilabel(panelConn, 'Position', [400 50 60 22], 'Text', 'SSH Key:');
txtKey = uieditfield(panelConn, 'text', 'Position', [470 50 250 22], ...
                     'Value', '~/.ssh/id_ed25519');

btnConnect = uibutton(panelConn, 'push', 'Text', 'Connect', ...
                      'Position', [10 10 100 30], ...
                      'ButtonPushedFcn', @(btn,event) onConnect());

btnDisconnect = uibutton(panelConn, 'push', 'Text', 'Disconnect', ...
                         'Position', [120 10 100 30], ...
                         'ButtonPushedFcn', @(btn,event) onDisconnect(), ...
                         'Enable', 'off');

btnDiscover = uibutton(panelConn, 'push', 'Text', 'Discover Nodes', ...
                       'Position', [730 10 120 30], ...
                       'ButtonPushedFcn', @(btn,event) onDiscover());

% Cluster info panel
panelCluster = uipanel(fig, 'Title', 'Cluster Information', ...
                       'Position', [20 400 860 140]);

btnListNodes = uibutton(panelCluster, 'push', 'Text', 'List Nodes', ...
                        'Position', [10 80 120 30], ...
                        'ButtonPushedFcn', @(btn,event) onListNodes());

btnSetupShared = uibutton(panelCluster, 'push', 'Text', 'Setup Shared Storage', ...
                          'Position', [140 80 150 30], ...
                          'ButtonPushedFcn', @(btn,event) onSetupShared());

uilabel(panelCluster, 'Position', [10 50 100 22], 'Text', 'Hosts File:');
txtHostsFile = uieditfield(panelCluster, 'text', 'Position', [120 50 200 22], ...
                           'Value', 'hosts.txt');

uilabel(panelCluster, 'Position', [10 20 100 22], 'Text', 'Shared Path:');
txtSharedPath = uieditfield(panelCluster, 'text', 'Position', [120 20 200 22], ...
                            'Value', '/srv/hpc/shared');

% Job submission panel
panelJob = uipanel(fig, 'Title', 'Job Submission', ...
                   'Position', [20 240 860 150]);

uilabel(panelJob, 'Position', [10 90 100 22], 'Text', 'Script:');
txtScript = uieditfield(panelJob, 'text', 'Position', [120 90 450 22]);
btnBrowse = uibutton(panelJob, 'push', 'Text', 'Browse...', ...
                     'Position', [580 90 80 22], ...
                     'ButtonPushedFcn', @(btn,event) onBrowseScript());

uilabel(panelJob, 'Position', [10 60 100 22], 'Text', '# Processes:');
spinProcs = uispinner(panelJob, 'Position', [120 60 80 22], ...
                      'Value', 4, 'Limits', [1 256]);

uilabel(panelJob, 'Position', [220 60 80 22], 'Text', 'Arguments:');
txtArgs = uieditfield(panelJob, 'text', 'Position', [310 60 260 22]);

chkGPU = uicheckbox(panelJob, 'Position', [590 60 80 22], ...
                    'Text', 'Use GPU');

btnSubmit = uibutton(panelJob, 'push', 'Text', 'Submit Job', ...
                     'Position', [10 20 120 30], ...
                     'ButtonPushedFcn', @(btn,event) onSubmit(), ...
                     'BackgroundColor', [0.2 0.7 0.3]);

btnListJobs = uibutton(panelJob, 'push', 'Text', 'List Jobs', ...
                       'Position', [140 20 100 30], ...
                       'ButtonPushedFcn', @(btn,event) onListJobs());

btnFetchLogs = uibutton(panelJob, 'push', 'Text', 'Fetch Logs', ...
                        'Position', [250 20 100 30], ...
                        'ButtonPushedFcn', @(btn,event) onFetchLogs());

% Log text area
uilabel(fig, 'Position', [20 210 100 22], 'Text', 'Log:');
txtLog = uitextarea(fig, 'Position', [20 20 860 180], ...
                    'Editable', 'off', 'Value', {});

% Manager object (stored in figure UserData)
fig.UserData = struct('mgr', [], 'lastJobId', '');

% --- Callback functions ---

    function onConnect()
        host = txtHost.Value;
        user = txtUser.Value;
        key = txtKey.Value;
        
        if isempty(host) || isempty(user)
            uialert(fig, 'Please enter host and username', 'Connection Error');
            return;
        end
        
        append(sprintf('Connecting to %s@%s...', user, host));
        
        try
            mgr = MacHPCClusterTools.Manager(host, user, key, 22);
            mgr.HostsFile = txtHostsFile.Value;
            mgr.SharedStorage = txtSharedPath.Value;
            mgr.connect();
            
            fig.UserData.mgr = mgr;
            append('Connected successfully');
            
            btnConnect.Enable = 'off';
            btnDisconnect.Enable = 'on';
        catch ME
            append(sprintf('Connection failed: %s', ME.message));
            uialert(fig, ME.message, 'Connection Error');
        end
    end

    function onDisconnect()
        mgr = fig.UserData.mgr;
        if ~isempty(mgr)
            mgr.disconnect();
            fig.UserData.mgr = [];
        end
        append('Disconnected');
        btnConnect.Enable = 'on';
        btnDisconnect.Enable = 'off';
    end

    function onDiscover()
        append('Discovering SSH-accessible nodes on network...');
        try
            hosts = MacHPCClusterTools.Network.discoverSSHHosts(4);
            if isempty(hosts)
                append('No hosts found on network');
                return;
            end
            
            for k = 1:numel(hosts)
                append(sprintf('  Found: %s (%s:%d)', hosts(k).name, ...
                       hosts(k).hostname, hosts(k).port));
            end
            
            assignin('base', 'MHC_discovered_hosts', hosts);
            append(sprintf('Discovered %d hosts (saved to workspace as MHC_discovered_hosts)', numel(hosts)));
        catch ME
            append(sprintf('Discovery failed: %s', ME.message));
        end
    end

    function onListNodes()
        mgr = fig.UserData.mgr;
        if isempty(mgr)
            uialert(fig, 'Not connected. Please connect first.', 'Error');
            return;
        end
        
        try
            nodes = mgr.listNodes();
            append(sprintf('Listed %d nodes from cluster', numel(nodes)));
        catch ME
            append(sprintf('Failed to list nodes: %s', ME.message));
        end
    end

    function onSetupShared()
        mgr = fig.UserData.mgr;
        if isempty(mgr)
            uialert(fig, 'Not connected. Please connect first.', 'Error');
            return;
        end
        
        try
            mgr.setupSharedStorage();
            append('Shared storage initialized');
        catch ME
            append(sprintf('Setup failed: %s', ME.message));
        end
    end

    function onBrowseScript()
        [file, path] = uigetfile('*.m', 'Select MATLAB script to submit');
        if isequal(file, 0)
            return;
        end
        txtScript.Value = fullfile(path, file);
    end

    function onSubmit()
        mgr = fig.UserData.mgr;
        if isempty(mgr)
            uialert(fig, 'Not connected. Please connect first.', 'Error');
            return;
        end
        
        scriptPath = txtScript.Value;
        if isempty(scriptPath) || ~exist(scriptPath, 'file')
            uialert(fig, 'Please select a valid MATLAB script', 'Error');
            return;
        end
        
        numProcs = spinProcs.Value;
        args = txtArgs.Value;
        useGPU = chkGPU.Value;
        hostsFile = txtHostsFile.Value;
        
        append(sprintf('Submitting %s with %d processes...', scriptPath, numProcs));
        
        try
            jobId = mgr.submit(scriptPath, ...
                              'numProcs', numProcs, ...
                              'hostsFile', hostsFile, ...
                              'useGPU', useGPU, ...
                              'args', args);
            
            fig.UserData.lastJobId = jobId;
            append(sprintf('Job submitted: %s', jobId));
            assignin('base', 'MHC_lastJobId', jobId);
        catch ME
            append(sprintf('Submit failed: %s', ME.message));
            uialert(fig, ME.message, 'Submission Error');
        end
    end

    function onListJobs()
        mgr = fig.UserData.mgr;
        if isempty(mgr)
            uialert(fig, 'Not connected. Please connect first.', 'Error');
            return;
        end
        
        try
            mgr.listJobs(20);
        catch ME
            append(sprintf('Failed to list jobs: %s', ME.message));
        end
    end

    function onFetchLogs()
        mgr = fig.UserData.mgr;
        if isempty(mgr)
            uialert(fig, 'Not connected. Please connect first.', 'Error');
            return;
        end
        
        jobId = fig.UserData.lastJobId;
        if isempty(jobId)
            answer = inputdlg('Enter Job ID:', 'Fetch Logs');
            if isempty(answer)
                return;
            end
            jobId = answer{1};
        end
        
        dest = uigetdir(pwd, 'Select destination for logs');
        if isequal(dest, 0)
            return;
        end
        
        append(sprintf('Fetching logs for job %s...', jobId));
        
        try
            mgr.fetch(jobId, dest);
            append(sprintf('Logs downloaded to %s', dest));
        catch ME
            append(sprintf('Fetch failed: %s', ME.message));
        end
    end

    function append(txt)
        timestamp = datestr(now, 'HH:MM:SS');
        txtLog.Value = [txtLog.Value; {sprintf('[%s] %s', timestamp, txt)}];
        
        % Auto-scroll to bottom
        drawnow;
        scroll(txtLog, 'bottom');
    end

end