classdef MacHPCClusterToolsApp < matlab.apps.AppBase
    % MacHPCClusterToolsApp  Programmatic App - Apple-like metal UI style A
    % This app provides two modes: Wizard (setup) and Job Manager.

    properties (Access = public)
        UIFigure             matlab.ui.Figure
        TabGroup             matlab.ui.container.TabGroup
        WizardTab            matlab.ui.container.Tab
        JobManagerTab        matlab.ui.container.Tab
        HostEdit             matlab.ui.control.EditField
        UserEdit             matlab.ui.control.EditField
        KeyEdit              matlab.ui.control.EditField
        BrowseKeyButton      matlab.ui.control.Button
        DiscoverButton       matlab.ui.control.Button
        SaveProfileButton    matlab.ui.control.Button
        ConnectButton        matlab.ui.control.Button
        DisconnectButton     matlab.ui.control.Button
        SubmitButton         matlab.ui.control.Button
        RefreshButton        matlab.ui.control.Button
        JobsTable            matlab.ui.control.Table
        LogArea              matlab.ui.control.TextArea
    end

    properties (Access = private)
        ManagerObj
        DiscoveredHosts
    end

    methods (Access = private)
        function appendLog(app, msg)
            ts = datestr(now, 'HH:MM:SS');
            val = app.LogArea.Value;
            if isempty(val)
                val = {sprintf('[%s] %s', ts, msg)};
            else
                val = [val; {sprintf('[%s] %s', ts, msg)}];
            end
            app.LogArea.Value = val;
            drawnow;
        end
    end

    methods (Access = public)
        function runWizard(app)
            app.TabGroup.SelectedTab = app.WizardTab;
            if ~isempty(app.ManagerObj)
                app.HostEdit.Value = app.ManagerObj.Host;
                app.UserEdit.Value = app.ManagerObj.User;
            end
        end
    end

    methods (Access = private)
        function onBrowseKey(app, event)
            [file, path] = uigetfile({'*','All Files (*.*)'});
            if isequal(file,0), return; end
            app.KeyEdit.Value = fullfile(path,file);
        end

        function onDiscover(app, event)
            app.appendLog('Discovering nodes via Bonjour...');
            try
                hosts = MacHPCClusterTools.Network.discoverSSHHosts(4);
                app.DiscoveredHosts = hosts;
                if isempty(hosts)
                    app.appendLog('No hosts discovered.');
                    uialert(app.UIFigure, 'No hosts found on the local network.', 'Discovery');
                    return;
                end
                for i = 1:numel(hosts)
                    app.appendLog(sprintf('Found: %s -> %s:%d', hosts(i).name, hosts(i).hostname, hosts(i).port));
                end
                uialert(app.UIFigure, sprintf('Discovered %d host(s).', numel(hosts)), 'Discovery');
            catch ME
                app.appendLog(['Discovery failed: ' ME.message]);
                uialert(app.UIFigure, ['Discovery failed: ' ME.message], 'Error');
            end
        end

        function onSaveProfile(app, event)
            cfg.Host = app.HostEdit.Value;
            cfg.User = app.UserEdit.Value;
            cfg.Key = app.KeyEdit.Value;
            cfg.SharedStorage = '/Users/Shared/HPC';
            try
                p = fullfile(getenv('HOME'), 'Library', 'Application Support', 'MacHPCClusterTools');
                if ~exist(p,'dir'), mkdir(p); end
                fp = fullfile(p, '.mhc_profile.json');
                fid = fopen(fp,'w'); fprintf(fid, jsonencode(cfg)); fclose(fid);
                app.appendLog(sprintf('Profile saved to %s', fp));
                uialert(app.UIFigure, 'Profile saved.', 'Success');
            catch ME
                app.appendLog(['Save profile failed: ' ME.message]);
                uialert(app.UIFigure, ['Save profile failed: ' ME.message], 'Error');
            end
        end

        function onConnect(app, event)
            if isempty(app.DiscoveredHosts)
                host = app.HostEdit.Value;
                port = 22;
            else
                host = app.DiscoveredHosts(1).hostname;
                port = app.DiscoveredHosts(1).port;
            end
            user = app.UserEdit.Value;
            key = app.KeyEdit.Value;
            app.appendLog(sprintf('Connecting to %s@%s:%d', user, host, port));
            try
                mgr = MacHPCClusterTools.Manager(host, user, key, port);
                mgr.connect();
                app.ManagerObj = mgr;
                app.appendLog('Connected. Manager stored.');
                app.RefreshButton.Enable = 'on';
                app.SubmitButton.Enable = 'on';
                app.DisconnectButton.Enable = 'on';
            catch ME
                app.appendLog(['Connect failed: ' ME.message]);
                uialert(app.UIFigure, ['Connect failed: ' ME.message], 'Connection failed');
            end
        end

        function onDisconnect(app, event)
            try
                if ~isempty(app.ManagerObj), app.ManagerObj.disconnect(); app.ManagerObj = []; end
                app.appendLog('Disconnected.');
                app.RefreshButton.Enable = 'off';
                app.SubmitButton.Enable = 'off';
                app.DisconnectButton.Enable = 'off';
            catch ME
                app.appendLog(['Disconnect error: ' ME.message]);
            end
        end

        function onSubmit(app, event)
            if isempty(app.ManagerObj)
                uialert(app.UIFigure, 'Not connected', 'Error');
                return;
            end
            [file, path] = uigetfile('*.m', 'Select MATLAB script to submit');
            if isequal(file,0), return; end
            fp = fullfile(path, file);
            app.appendLog(sprintf('Submitting %s ...', fp));
            try
                jobId = app.ManagerObj.submit(fp, 'cpus', 2, 'mem', '4G', 'time', '01:00:00');
                app.appendLog(sprintf('Submitted job %s', jobId));
                app.refreshJobs();
            catch ME
                app.appendLog(['Submit failed: ' ME.message]);
                uialert(app.UIFigure, ['Submit failed: ' ME.message], 'Submit');
            end
        end

        function onRefresh(app, event)
            app.refreshJobs();
        end

        function refreshJobs(app)
            if isempty(app.ManagerObj)
                app.appendLog('Not connected. Cannot refresh jobs.');
                return;
            end
            try
                user = app.ManagerObj.User;
                [s,out] = app.ManagerObj.SSH.exec(sprintf('squeue -u %s -o "%%i %%t %%M %%L %%j" -h', user));
                if s~=0, app.appendLog(['squeue failed: ' out]); return; end
                lines = strsplit(strtrim(out), char(10));
                rows = {};
                for i=1:numel(lines)
                    ln = strtrim(lines{i});
                    if isempty(ln), continue; end
                    toks = regexp(ln, '\s+', 'split');
                    if numel(toks) >= 5
                        rows(end+1,:) = {toks{1}, toks{2}, toks{3}, toks{4}, toks{5}}; %#ok<AGROW>
                    end
                end
                if isempty(rows)
                    app.JobsTable.Data = {};
                else
                    app.JobsTable.Data = rows;
                end
                app.appendLog('Jobs refreshed.');
            catch ME
                app.appendLog(['Refresh failed: ' ME.message]);
            end
        end
    end

    methods (Access = private)
        function createComponents(app)
            app.UIFigure = uifigure('Name','MacHPCClusterTools','Position',[200 200 1000 650],'Color',[0.96 0.96 0.98]);

            app.TabGroup = uitabgroup(app.UIFigure,'Position',[10 10 980 630]);
            app.WizardTab = uitab(app.TabGroup,'Title','Wizard');
            app.JobManagerTab = uitab(app.TabGroup,'Title','Job Manager');

            uilabel(app.WizardTab,'Position',[20 560 300 28],'Text','Welcome to MacHPCClusterTools Setup','FontSize',16,'FontWeight','bold');
            uilabel(app.WizardTab,'Position',[20 520 80 22],'Text','Host:');
            app.HostEdit = uieditfield(app.WizardTab,'text','Position',[100 520 260 22]);
            uilabel(app.WizardTab,'Position',[380 520 40 22],'Text','User:');
            app.UserEdit = uieditfield(app.WizardTab,'text','Position',[420 520 160 22]);
            uilabel(app.WizardTab,'Position',[20 480 80 22],'Text','Private key:');
            app.KeyEdit = uieditfield(app.WizardTab,'text','Position',[100 480 380 22]);
            app.BrowseKeyButton = uibutton(app.WizardTab,'push','Text','Browse','Position',[490 480 80 22],'ButtonPushedFcn',@(btn,event) app.onBrowseKey(event));
            app.DiscoverButton = uibutton(app.WizardTab,'push','Text','Discover Nodes','Position',[20 430 140 30],'ButtonPushedFcn',@(btn,event) app.onDiscover(event));
            app.SaveProfileButton = uibutton(app.WizardTab,'push','Text','Save Profile','Position',[180 430 140 30],'ButtonPushedFcn',@(btn,event) app.onSaveProfile(event));

            uilabel(app.JobManagerTab,'Position',[20 560 300 28],'Text','Job Manager','FontSize',16,'FontWeight','bold');
            app.ConnectButton = uibutton(app.JobManagerTab,'push','Text','Connect','Position',[20 520 100 30],'ButtonPushedFcn',@(btn,event) app.onConnect(event));
            app.DisconnectButton = uibutton(app.JobManagerTab,'push','Text','Disconnect','Position',[140 520 100 30],'ButtonPushedFcn',@(btn,event) app.onDisconnect(event),'Enable','off');
            app.SubmitButton = uibutton(app.JobManagerTab,'push','Text','Submit Script','Position',[260 520 120 30],'ButtonPushedFcn',@(btn,event) app.onSubmit(event),'Enable','off');
            app.RefreshButton = uibutton(app.JobManagerTab,'push','Text','Refresh Jobs','Position',[400 520 120 30],'ButtonPushedFcn',@(btn,event) app.onRefresh(event),'Enable','off');

            app.JobsTable = uitable(app.JobManagerTab,'Position',[20 120 600 380],'ColumnName',{'JobID','State','RunTime','TimeLeft','Name'});
            app.LogArea = uitextarea(app.JobManagerTab,'Position',[640 120 320 380],'Editable','off');
        end
    end

    methods (Access = public)
        function app = MacHPCClusterToolsApp
            createComponents(app);
            app.ManagerObj = MacHPCClusterTools.Manager('', '', '', 22);
            app.HostEdit.Value = '';
            app.UserEdit.Value = '';
            app.KeyEdit.Value = '';
            app.TabGroup.SelectedTab = app.WizardTab;
        end

        function delete(app)
            try
                if ~isempty(app.ManagerObj), app.ManagerObj.disconnect(); end
            catch
            end
            delete(app.UIFigure);
        end
    end
end
