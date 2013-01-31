#!/usr/local/bin/python2.7

from __future__ import print_function

import os
import sys
import appdirs
import logging
import shlex

try:
    import cmd
except:
    print("failed to import cmd, interactive mode not supported")
    raise

readline_loaded = False
try:
    import readline
    readline_loaded = True
except ImportError:
    try:
        import pyreadline as readline
        readline_loaded = True
    except ImportError:
        print("failed to import pyreadline, readline functionality not supported")
        raise

import instlInstanceBase
from aYaml import augmentedYaml

def insensitive_glob(pattern):
    import glob
    def either(c):
        return '[%s%s]'%(c.lower(),c.upper()) if c.isalpha() else c
    return glob.glob(''.join(map(either,pattern)))

def go_interactive(instl_inst):
    try:
        instlInstanceBase.InstlInstanceBase.create_completion_list = create_completion_list_imp
        instlInstanceBase.InstlInstanceBase.do_list = do_list_imp
        with instlCMD(instl_inst) as icmd:
            icmd.cmdloop()
    except Exception as es:
        import traceback
        tb = traceback.format_exc()
        print("go_interactive", es, tb)

def restart_program():
    """Restarts the current program.
        Note: this function does not return. Any cleanup action (like
        saving data) must be done before calling this function."""
    python = sys.executable
    os.execl(python, python, * sys.argv)

class instlCMD(cmd.Cmd, object):
    def __init__(self, instl_inst):
        cmd.Cmd.__init__(self)
        self.instl_inst = instl_inst
        self.restart = False

    def __enter__(self):
        if readline_loaded:
            readline.parse_and_bind ("bind ^I rl_complete") # Enable tab completions on MacOS
            readline.parse_and_bind("tab: complete")        # and on other OSs
            readline.parse_and_bind("set completion-ignore-case on")
            readline.parse_and_bind("set show-all-if-ambiguous on")
            readline.parse_and_bind("set completion-map-case on")
            readline.parse_and_bind("set show-all-if-unmodified on")
            readline.parse_and_bind("set expand-tilde on")
            history_file_dir = appdirs.user_data_dir("instl", "Waves Audio")
            try:
                os.makedirs(history_file_dir)
            except: # os.makedirs raises is the directory already exists
                pass
            self.history_file_path = os.path.join(history_file_dir, ".instl_console_history")
            if os.path.isfile(self.history_file_path):
                readline.read_history_file(self.history_file_path)
        self.prompt = "instl: "
        self.save_dir = os.getcwd()
        return self

    def __exit__(self, type, value, traceback):
        if readline_loaded:
            # restart only after saving history, otherwise history will not be saved (8-().
            readline.set_history_length(1024)
            readline.write_history_file(self.history_file_path)
        os.chdir(self.save_dir)
        if self.restart:
            restart_program()

    def path_completion(self, text, line, begidx, endidx):
        matches = []
        if text:
            try:
                matches.extend(insensitive_glob(text+'*'))
            except Exception as es:
                logging.info(es)
        return matches

    def dir_completion(self, text, line, begidx, endidx):
        matches = []
        if text:
            try:
                matches.extend([dir for dir in insensitive_glob(text+'*') if os.path.isdir(dir)])
            except Exception as es:
                logging.info(es)
        return matches

    def do_shell(self, s):
        if s:
            os.system(s)
        return False

    def help_shell(self):
        print("execute shell commands")

    def do_cd(self, s):
        if os.path.isdir(s):
            os.chdir(s)
        else:
            print(s, "is not a directory")
        return False

    def complete_cd(self, text, line, begidx, endidx):
        return self.dir_completion(text, line, begidx, endidx)

    def help_cd(self):
        print("cd path, change current directory")

    def do_list(self, params):
        try:
            if params:
                for param in params.split():
                    if param[-1] == '*':
                        identifier_list = self.indentifier_completion_list(param[:-1], params, 0, 0)
                        self.instl_inst.do_list(identifier_list)
                    else:
                        identifier_list = self.indentifier_completion_list(param, params, 0, 0)
                        if identifier_list:
                            self.instl_inst.do_list(identifier_list)
                        else:
                            print("Unknown identifier:", param)
            else:
                self.instl_inst.do_list()
        except Exception as es:
            print("list", es)
        return False

    def indentifier_completion_list(self, text, line, begidx, endidx):
        matches = []
        if text:
            completion_list = self.instl_inst.create_completion_list()
            if completion_list:
                matches.extend([s for s in completion_list
                         if s and s.lower().startswith(text.lower())])
        return matches

    def complete_list(self, text, line, begidx, endidx):
        #print("complete_list, text:", text)
        matches = self.indentifier_completion_list(text, line, begidx, endidx)
        for s in ("define", "index"):
            if s.lower().startswith(text.lower()):
                matches.append(s)
        return matches

    def help_list(self):
        print( "list define" )
        print( "    lists all definitions" )
        print( "list index" )
        print( "    lists all index entries" )
        print( "list" )
        print( "    lists all definitions & index entries" )
        print( "list indentifier[*]" )
        print( "    lists variable(*)" )

    def do_set(self, params):
        if params:
            params = shlex.split(params)
            identi, values = params[0], params[1:]
            self.instl_inst.cvl.set_variable(identi, "set interactively", values)
            self.instl_inst.resolve()
            self.do_list(identi)
            
    def complete_set(self, text, line, begidx, endidx):
        return self.indentifier_completion_list(text, line, begidx, endidx)

    def help_set(self):
        print("set identifier [value, ...]")
        print("    set values of variable")
            
    def do_del(self, params):
        for identi in params.split():
            del self.instl_inst.cvl[identi]
            
    def complete_del(self, text, line, begidx, endidx):
        return self.indentifier_completion_list(text, line, begidx, endidx)

    def help_del(self):
        print("del [identifier, ...]")
        print("    deletes a variable")
          
    def do_read(self, params):
        if params:
            for file in shlex.split(params):
                try:
                    self.instl_inst.read_file(file)
                    self.instl_inst.resolve()
                except Exception as ex:
                    print("read", filem, ex)
        else:
            print("read what?")
        return False

    def complete_read(self, text, line, begidx, endidx):
        return self.path_completion(text, line, begidx, endidx)

    def do_write(self, params):
        self.instl_inst.dedigest()
        self.instl_inst.digest()
        self.instl_inst.create_install_instructions()
        outfile = "stdout"
        if params:
            outfile = shlex.split(params)[0]
        main_out_file_obj = self.instl_inst.cvl.get_configVar_obj("__MAIN_OUT_FILE__")
        main_out_file_obj.clear_values()
        main_out_file_obj.append(outfile)
        self.instl_inst.resolve()
        self.instl_inst.write_install_batch_file()
        return False

    def complete_write(self, text, line, begidx, endidx):
        return self.path_completion(text, line, begidx, endidx)

    def do_restart(self, params):
        print("restarting instl")
        self.restart = True
        return True # stops cmdloop

    def help_restart(self):
        print("restart:", "reloads instl")

    def do_quit(self, params):
        return True

    def do_q(self, params):
        return self.do_quit(params)

    def default(self, line):
        print("unknown command: ", line)
        return False

    # evaluate python expressions
    def do_eval(self, param):
        try:
            if param:
                print(eval(param))
        except Exception as ex:
            print("eval:",  ex)
            
    def help_eval(self):
        print("evaluate python expressions, instlInstance is accessible as self.instl_inst")

def do_list_imp(self, what = None):
    if what is None:
        augmentedYaml.writeAsYaml(self, sys.stdout)
    elif isinstance(what, list):
        item_list = self.repr_for_yaml(what)
        for item in item_list:
            augmentedYaml.writeAsYaml(item, sys.stdout)
    elif isinstance(what, str):
        if what == "define":
            augmentedYaml.writeAsYaml(augmentedYaml.YamlDumpDocWrap(self.cvl, '!define', "Definitions", explicit_start=True, sort_mappings=True), sys.stdout)
        elif what == "index":
            augmentedYaml.writeAsYaml(augmentedYaml.YamlDumpDocWrap(self.install_definitions_index, '!index', "Installation index", explicit_start=True, sort_mappings=True), sys.stdout)
        else:
            item_list = self.repr_for_yaml(what)
            for item in item_list:
                augmentedYaml.writeAsYaml(item, sys.stdout)


def create_completion_list_imp(self):
    retVal = list()
    try:
        retVal.extend(self.install_definitions_index.keys())
        retVal.extend(self.cvl.keys())
    except Exception as ex:
        print("create_completion_list:",   ex)
    return retVal
