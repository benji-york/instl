
from .configVarStack import config_vars
from .configVarStack import private_config_vars
from .configVarYamlReader import ConfigVarYamlReader, eval_conditional
var_stack = config_vars  # for backward compatibility of scripts executed with "exec" command
