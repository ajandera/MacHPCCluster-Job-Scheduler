classdef Agent
    methods(Static)
        function status = hasAgent()
            % Check if SSH agent has keys loaded (macOS)
            [s,~] = system('ssh-add -l >/dev/null 2>&1; echo $?');
            status = (s==0);
        end
    end
end
