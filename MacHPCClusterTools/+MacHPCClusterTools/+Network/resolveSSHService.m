function info = resolveSSHService(serviceName)
info = struct('name','','regtype','_ssh._tcp','domain','local','hostname','','port',[]);
if isempty(serviceName), return; end
cmd = sprintf('dns-sd -L "%s" _ssh._tcp local 2>&1', serviceName);
[status,out] = system(cmd);
lines = strsplit(out, char(10));
hostname=''; port=[];
for i=1:numel(lines)
    ln = strtrim(lines{i});
    m = regexp(ln, 'can be reached at ([^\.:]+(?:\.local)?)(?:\.|:)(\d+)', 'tokens', 'once');
    if ~isempty(m)
        hostname = m{1}; port = str2double(m{2}); break;
    end
    m2 = regexp(ln, 'address = ([0-9\.]+).*port = (\d+)', 'tokens', 'once');
    if ~isempty(m2)
        hostname = m2{1}; port = str2double(m2{2}); break;
    end
end
if isempty(hostname)
    candidate = [serviceName '.local'];
    [s,~] = system(sprintf('ping -c 1 -t 1 %s 2>/dev/null || true', candidate));
    if s==0, hostname = candidate; port = 22; end
end
info.name = serviceName; info.hostname = hostname; info.port = port;
end
