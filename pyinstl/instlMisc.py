#!/usr/bin/env python3

import re
import os
import stat
import sys
import shlex
import tarfile
import time
import filecmp
import zlib

import utils
from collections import OrderedDict
from .instlInstanceBase import InstlInstanceBase
from configVar import config_vars
from . import connectionBase
from pybatch import *


# noinspection PyUnresolvedReferences,PyUnresolvedReferences,PyUnresolvedReferences
class InstlMisc(InstlInstanceBase):
    def __init__(self, initial_vars, command) -> None:
        super().__init__(initial_vars)
        # noinspection PyUnresolvedReferences
        self.read_defaults_file(super().__thisclass__.__name__)
        self.curr_progress = 0
        self.total_progress = 0
        self.progress_staccato_command = False
        self.progress_staccato_period = 1
        self.progress_staccato_count = 0

        if command in ("exec", "resolve"):
            self.need_items_table = True
        if command in ("check-checksum", "set-exec", "create-folders", "command-list"):
            self.need_info_map_table = True

    def get_default_out_file(self):
        retVal = None
        if self.fixed_command in ("ls", "resolve"):
            retVal = "stdout"
        return retVal

    def do_command(self):
        self.no_numbers_progress =  bool(config_vars.get("__NO_NUMBERS_PROGRESS__", "False"))
        # if var does not exist default is 0, meaning not to display dynamic progress
        self.curr_progress = int(config_vars.get("__START_DYNAMIC_PROGRESS__", "0"))
        self.total_progress = int(config_vars.get("__TOTAL_DYNAMIC_PROGRESS__", "0"))
        self.progress_staccato_period = int(config_vars["PROGRESS_STACCATO_PERIOD"])
        self.progress_staccato_count = 0
        do_command_func = getattr(self, "do_" + self.fixed_command)
        before_time = time.perf_counter()
        do_command_func()
        after_time = time.perf_counter()
        if bool(config_vars["PRINT_COMMAND_TIME"]):
            print(self.the_command, "time:", round(after_time - before_time, 4), "sec.")

    def dynamic_progress(self, msg):
        if self.total_progress > 0:
            self.progress_staccato_count = (self.progress_staccato_count + 1) % self.progress_staccato_period
            self.curr_progress += 1
            if not self.progress_staccato_command or self.progress_staccato_count == 0:
                print(f"Progress: {self.curr_progress} of {self.total_progress}; {msg}")
        elif self.no_numbers_progress:
            print(f"Progress: ... of ...; {msg}")

    def do_version(self):
        config_vars["PRINT_COMMAND_TIME"] = "no" # do not print time report
        print(self.get_version_str())

    def do_help(self):
        import pyinstl.helpHelper
        config_vars["PRINT_COMMAND_TIME"] = "no" # do not print time report

        help_folder_path = os.path.join(config_vars["__INSTL_DATA_FOLDER__"].str(), "help")
        pyinstl.helpHelper.do_help(config_vars["__HELP_SUBJECT__"].str(), help_folder_path, self)

    def do_parallel_run(self):
        processes_list_file = config_vars["__MAIN_INPUT_FILE__"].str()
        with ParallelRun(processes_list_file, shell=False)as para_runner:
            para_runner()

    def do_wtar(self):
        what_to_work_on = config_vars["__MAIN_INPUT_FILE__"].str()
        if not os.path.exists(what_to_work_on):
            print(what_to_work_on, "does not exists")
            return

        what_to_work_on_dir, what_to_work_on_leaf = os.path.split(what_to_work_on)

        where_to_put_wtar = None
        if "__MAIN_OUT_FILE__" in config_vars:
            where_to_put_wtar = config_vars["__MAIN_OUT_FILE__"].str()

        with Wtat(what_to_wtar=what_to_work_on, where_to_put_wtar=where_to_put_wtar) as wtarrer:
            wtarrer()

    def do_unwtar(self):
        self.no_artifacts =  bool(config_vars["__NO_WTAR_ARTIFACTS__"])
        what_to_work_on = str(config_vars.get("__MAIN_INPUT_FILE__", '.'))
        what_to_work_on_dir, what_to_work_on_leaf = os.path.split(what_to_work_on)
        where_to_unwtar = None
        if "__MAIN_OUT_FILE__" in config_vars:
            where_to_unwtar = config_vars["__MAIN_OUT_FILE__"].str()

        with Unwtar(what_to_work_on, where_to_unwtar, self.no_artifacts) as uwtarrer:
            uwtarrer()
        self.dynamic_progress(f"unwtar {utils.original_name_from_wtar_name(what_to_work_on_leaf)}")

    def do_check_checksum(self):
        self.progress_staccato_command = True
        bad_checksum_list = list()
        missing_files_list = list()
        self.read_info_map_from_file(config_vars["__MAIN_INPUT_FILE__"].str())
        for file_item in self.info_map_table.get_items(what="file"):
            if os.path.isfile(file_item.download_path):
                file_checksum = utils.get_file_checksum(file_item.download_path)
                if not utils.compare_checksums(file_checksum, file_item.checksum):
                    bad_checksum_list.append(" ".join(("Bad checksum:", file_item.download_path, "expected", file_item.checksum, "found", file_checksum)) )
            else:
                missing_files_list.append(" ".join((file_item.download_path, "was not found")))
            self.dynamic_progress(f"Check checksum {file_item.path}")
        if bad_checksum_list or missing_files_list:
            bad_checksum_list_exception_message = ""
            missing_files_exception_message = ""
            if bad_checksum_list:
                print("\n".join(bad_checksum_list))
                bad_checksum_list_exception_message += f"Bad checksum for {len(bad_checksum_list)} files"
                print(bad_checksum_list_exception_message)
            if missing_files_list:
                print("\n".join(missing_files_list))
                missing_files_exception_message += f"Missing {len(missing_files_list)} files"
                print(missing_files_exception_message)
            raise ValueError("\n".join((bad_checksum_list_exception_message, missing_files_exception_message)))

    def do_set_exec(self):
        self.progress_staccato_command = True
        self.read_info_map_from_file(config_vars["__MAIN_INPUT_FILE__"].str())
        for file_item_path in self.info_map_table.get_exec_file_paths():
            if os.path.isfile(file_item_path):
                file_stat = os.stat(file_item_path)
                os.chmod(file_item_path, file_stat.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            self.dynamic_progress(f"Set exec {file_item_path}")

    def do_create_folders(self):
        self.progress_staccato_command = True
        self.read_info_map_from_file(config_vars["__MAIN_INPUT_FILE__"].str())
        for dir_item in self.info_map_table.get_items(what="dir"):
            os.makedirs(dir_item.path, exist_ok=True)
            self.dynamic_progress(f"Create folder {dir_item.path}")

    def do_test_import(self):
        import importlib

        bad_modules = list()
        for module in ("yaml", "appdirs", "configVar", "utils", "svnTree", "aYaml"):
            try:
                importlib.import_module(module)
            except ImportError:
                bad_modules.append(module)
        if len(bad_modules) > 0:
            print("missing modules:", bad_modules)
            sys.exit(17)

    def do_remove_empty_folders(self):
        folder_to_remove = config_vars["__MAIN_INPUT_FILE__"].str()
        files_to_ignore = list(config_vars.get("REMOVE_EMPTY_FOLDERS_IGNORE_FILES", []))
        for root_path, dir_names, file_names in os.walk(folder_to_remove, topdown=False, onerror=None, followlinks=False):
            # when topdown=False os.walk creates dir_names for each root_path at the beginning and has
            # no knowledge if a directory has already been deleted.
            existing_dirs = [dir_name for dir_name in dir_names if os.path.isdir(os.path.join(root_path, dir_name))]
            if len(existing_dirs) == 0:
                ignored_files = list()
                for filename in file_names:
                    if filename in files_to_ignore:
                        ignored_files.append(filename)
                    else:
                        break
                if len(file_names) == len(ignored_files):
                    # only remove the ignored files if the folder is to be removed
                    for filename in ignored_files:
                        file_to_remove_full_path = os.path.join(root_path, filename)
                        try:
                            os.remove(file_to_remove_full_path)
                        except Exception as ex:
                            print("failed to remove", file_to_remove_full_path, ex)
                    try:
                        os.rmdir(root_path)
                    except Exception as ex:
                        print("failed to remove", root_path, ex)

    def do_win_shortcut(self):
        shortcut_path = config_vars["__SHORTCUT_PATH__"].str()
        target_path = config_vars["__SHORTCUT_TARGET_PATH__"].str()
        run_as_admin =  bool(config_vars.get("__RUN_AS_ADMIN__", "False"))
        with WinShortcut(shortcut_path, target_path, run_as_admin) as short_cutter:
            short_cutter()

    def do_translate_url(self):
        url_to_translate = config_vars["__MAIN_INPUT_FILE__"].str()
        translated_url = connectionBase.connection_factory().translate_url(url_to_translate)
        print(translated_url)

    def do_mac_dock(self):
        path_to_item = str(config_vars.get("__DOCK_ITEM_PATH__", ""))
        label_for_item = str(config_vars.get("__DOCK_ITEM_LABEL__", ""))
        restart_the_doc = bool(config_vars["__RESTART_THE_DOCK__"])
        remove = bool(config_vars["__REMOVE_FROM_DOCK__"])

        with MacDock(path_to_item, label_for_item, restart_the_doc, remove) as mac_docker:
            mac_docker()

    def do_ls(self):
        main_folder_to_list = config_vars["__MAIN_INPUT_FILE__"].str()
        folders_to_list = []
        if config_vars.defined("__LIMIT_COMMAND_TO__"):
            limit_list = list(config_vars["__LIMIT_COMMAND_TO__"])
            for limit in limit_list:
                limit = utils.unquoteme(limit)
                folders_to_list.append(os.path.join(main_folder_to_list, limit))
        else:
            folders_to_list.append(main_folder_to_list)

        ls_format = str(config_vars.get("LS_FORMAT", '*'))
        the_listing = utils.disk_item_listing(*folders_to_list, ls_format=ls_format)

        out_file = config_vars["__MAIN_OUT_FILE__"].str()
        try:
            with utils.write_to_file_or_stdout(out_file) as wfd:
                wfd.write(the_listing)
        except NotADirectoryError:
            print(f"Cannot output to {out_file}")

    def do_fail(self):
        exit_code = int(config_vars.get("__FAIL_EXIT_CODE__", "1") )
        print("Failing on purpose with exit code", exit_code)
        sys.exit(exit_code)

    def do_checksum(self):
        path_to_checksum = config_vars["__MAIN_INPUT_FILE__"].str()
        ignore_files = list(config_vars.get("WTAR_IGNORE_FILES", []))
        checksums_dict = utils.get_recursive_checksums(path_to_checksum, ignore=ignore_files)
        total_checksum = checksums_dict.pop('total_checksum', "Unknown total checksum")
        path_and_checksum_list = [(path, checksum) for path, checksum in sorted(checksums_dict.items())]
        width_list, align_list = utils.max_widths(path_and_checksum_list)
        col_formats = utils.gen_col_format(width_list, align_list)
        for p_and_c in path_and_checksum_list:
            print(col_formats[len(p_and_c)].format(*p_and_c))
        print()
        print(col_formats[2].format("total checksum", total_checksum))

    def do_resolve(self):
        config_vars["PRINT_COMMAND_TIME"] = "no" # do not print time report
        config_file = config_vars["__CONFIG_FILE__"].str()
        if not os.path.isfile(config_file):
            raise FileNotFoundError(config_file, config_vars["__CONFIG_FILE__"].raw())
        input_file = config_vars["__MAIN_INPUT_FILE__"].str()
        if not os.path.isfile(input_file):
            raise FileNotFoundError(input_file, config_vars["__MAIN_INPUT_FILE__"].raw())
        output_file = config_vars["__MAIN_OUT_FILE__"].str()
        self.read_yaml_file(config_file)
        with utils.utf8_open(input_file, "r") as rfd:
            text_to_resolve = rfd.read()
        resolved_text = config_vars.resolve_str(text_to_resolve)
        with utils.utf8_open(output_file, "w") as wfd:
            wfd.write(resolved_text)

    def do_exec(self):
        py_file_path = "unknown file"
        try:
            self.read_yaml_file("InstlClient.yaml")  # temp hack, which additional config file to read should come from command line options
            config_file = config_vars["__CONFIG_FILE__"].str()
            self.read_yaml_file(config_file, ignore_if_not_exist=True)
            py_file_path = config_vars["__MAIN_INPUT_FILE__"].str()
            with utils.utf8_open(py_file_path, 'r') as rfd:
                py_text = rfd.read()
                exec(py_text, globals())
        except Exception as ex:
            print("Exception while exec ", py_file_path, ex)

    def do_wzip(self):
        """ Create a new wzip for a file  provided in '--in' command line option

            If --out is not supplied on the command line the new wzip file will be created
                next to the input with extension '.wzip'.
                e.g. the command:
                    instl wzip --in /a/b/c
                will create the wzip file at path:
                    /a/b/c.wzip

            If '--out' is supplied and it's an existing file, the new wzip will overwrite
                this existing file, wzip extension will NOT be added.
                e.g. assuming /d/e/f.txt is an existing file, the command:
                    instl wzip --in /a/b/c --out /d/e/f.txt
                will create the wzip file at path:
                    /d/e/f.txt

            if '--out' is supplied and is and existing folder the wzip file will be created
                inside this folder with extension '.wzip'.
                e.g. assuming /g/h/i is an existing folder, the command:
                    instl wzip --in /a/b/c --out /g/h/i
                will create the wzip file at path:
                    /g/h/i/c.wzip

            if '--out' is supplied and does not exists, the folder will be created
                and the wzip file will be created inside the new folder with extension
                 '.wzip'.
                e.g. assuming /j/k/l is a non existing folder, the command:
                    instl wzip --in /a/b/c --out /j/k/l
                will create the wzip file at path:
                    /j/k/l/c.wzip

            configVar effecting wzip:
            ZLIB_COMPRESSION_LEVEL: will set the compression level, default is 8
            WZLIB_EXTENSION: .wzip extension is the default, the value is read from the configVar WZLIB_EXTENSION,
        """
        what_to_work_on = config_vars["__MAIN_INPUT_FILE__"].str()
        if not os.path.exists(what_to_work_on):
            print(what_to_work_on, "does not exists")
            return

        what_to_work_on_dir, what_to_work_on_leaf = os.path.split(what_to_work_on)

        where_to_put_wzip = None
        if "__MAIN_OUT_FILE__" in config_vars:
            where_to_put_wzip = config_vars["__MAIN_OUT_FILE__"].str()
        else:
            where_to_put_wzip = what_to_work_on_dir
            if not where_to_put_wzip:
                where_to_put_wzip = "."

        if os.path.isfile(where_to_put_wzip):
            target_wzip_file = where_to_put_wzip
        else:  # assuming it's a folder
            os.makedirs(where_to_put_wzip, exist_ok=True)
            target_wzip_file = os.path.join(where_to_put_wzip, what_to_work_on_leaf+".wzip")

        zlib_compression_level = int(config_vars.get("ZLIB_COMPRESSION_LEVEL", "8"))
        with open(target_wzip_file, "wb") as wfd:
            wfd.write(zlib.compress(open(what_to_work_on, "r").read().encode(), zlib_compression_level))
