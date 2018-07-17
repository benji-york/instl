#!/usr/bin/env python3


import os
import abc
import itertools
import pathlib
import sys
import functools
import random
import string

import utils
from configVar import config_vars  # √
from . import connectionBase


class CopyToolBase(object, metaclass=abc.ABCMeta):
    """ Create copy commands. Each function should be overridden to implement the copying
        on specific platform using a specific copying tool. All functions return
        a list of commands, even if there is only one. This will allow to return
        multiple commands if needed.
    """

    def __init__(self, platform_helper) -> None:
        self.platform_helper = platform_helper

    @abc.abstractmethod
    def finalize(self):
        pass

    @abc.abstractmethod
    def begin_copy_folder(self):
        pass

    @abc.abstractmethod
    def end_copy_folder(self):
        pass

    @abc.abstractmethod
    def copy_dir_to_dir(self, src_dir, trg_dir, link_dest=False, ignore=None, preserve_dest_files=False):
        """ Copy src_dir as a folder into trg_dir.
            Example: copy_dir_to_dir("a", "/d/c/b") creates the folder:
            "/d/c/b/a"
        """
        pass

    @abc.abstractmethod
    def copy_file_to_dir(self, src_file, trg_dir, link_dest=False, ignore=None):
        """ Copy the file src_file into trg_dir.
            Example: copy_file_to_dir("a.txt", "/d/c/b") creates the file:
            "/d/c/b/a.txt"
        """
        pass

    @abc.abstractmethod
    def copy_dir_contents_to_dir(self, src_dir, trg_dir, link_dest=False, ignore=None, preserve_dest_files=True):
        """ Copy the contents of src_dir into trg_dir.
            Example: copy_dir_contents_to_dir("a", "/d/c/b") copies
            everything from a into "/d/c/b"
        """
        pass

    @abc.abstractmethod
    def copy_file_to_file(self, src_file, trg_file, link_dest=False, ignore=None):
        """ Copy file src_file into trg_file.
            Example: copy_file_to_file("a", "/d/c/b") copies
            the file a to the file "/d/c/b".
        """
        pass

    @abc.abstractmethod
    def remove_file(self, file_to_remove):
        pass

    @abc.abstractmethod
    def remove_dir(self, dir_to_remove):
        pass


class CopyToolRsync(CopyToolBase):
    def __init__(self, platform_helper) -> None:
        super().__init__(platform_helper)

    def finalize(self):
        pass

    def begin_copy_folder(self):
        return ()

    def end_copy_folder(self):
        return ()

    def create_ignore_spec(self, ignore: bool):
        retVal = ""
        if ignore:
            if isinstance(ignore, str):
                ignore = (ignore,)
            retVal = " ".join(["--exclude=" + utils.quoteme_single(ignoree) for ignoree in ignore])
        return retVal

    def copy_dir_to_dir(self, src_dir, trg_dir, link_dest=False, ignore=None, preserve_dest_files=False):
        if src_dir.endswith("/"):
            src_dir.rstrip("/")
        ignore_spec = self.create_ignore_spec(ignore)
        if not preserve_dest_files:
            delete_spec = "--delete"
        else:
            delete_spec = ""
        if link_dest:
            the_link_dest = os.path.join(src_dir, "..")
            sync_command = f"""rsync --owner --group -l -r -E {delete_spec} {ignore_spec} --link-dest="{the_link_dest}" "{src_dir}" "{trg_dir}" """
        else:
            sync_command = f"""rsync --owner --group -l -r -E {delete_spec} {ignore_spec} "{src_dir}" "{trg_dir}" """

        return sync_command

    def copy_file_to_dir(self, src_file, trg_dir, link_dest=False, ignore=None):
        assert not src_file.endswith("/")
        if not trg_dir.endswith("/"):
            trg_dir += "/"
        ignore_spec = self.create_ignore_spec(ignore)
        permissions_spec = str(config_vars.get("RSYNC_PERM_OPTIONS", ""))
        if link_dest:
            the_link_dest, src_file_name = os.path.split(src_file)
            relative_link_dest = os.path.relpath(the_link_dest, trg_dir)
            sync_command = f"""rsync --owner --group -l -r -E {ignore_spec} --link-dest="{relative_link_dest}" "{src_file}" "{trg_dir}" """
        else:
            sync_command = f"""rsync --owner --group -l -r -E {ignore_spec} "{src_file}" "{trg_dir}" """

        return sync_command

    def copy_file_to_file(self, src_file, trg_file, link_dest=False, ignore=None):
        assert not src_file.endswith("/")
        ignore_spec = self.create_ignore_spec(ignore)
        if link_dest:
            src_folder_name, src_file_name = os.path.split(src_file)
            trg_folder_name, trg_file_name = os.path.split(trg_file)
            relative_link_dest = os.path.relpath(src_folder_name, trg_folder_name)
            sync_command = f"""rsync --owner --group -l -r -E {ignore_spec} --link-dest="{relative_link_dest}" "{src_file}" "{trg_file}" """
        else:
            sync_command = f"""rsync --owner --group -l -r -E {ignore_spec} "{src_file}" "{trg_file}" """

        return sync_command

    def copy_dir_contents_to_dir(self, src_dir, trg_dir, link_dest=False, ignore=None, preserve_dest_files=True):
        if not src_dir.endswith("/"):
            src_dir += "/"
        ignore_spec = self.create_ignore_spec(ignore)
        delete_spec = ""
        if not preserve_dest_files:
            delete_spec = "--delete"
        else:
            delete_spec = ""
        if link_dest:
            relative_link_dest = os.path.relpath(src_dir, trg_dir)
            sync_command = f"""rsync --owner --group -l -r -E {delete_spec} {ignore_spec} --link-dest="{relative_link_dest}" "{src_dir}" "{trg_dir}" """
        else:
            sync_command = f"""rsync --owner --group -l -r -E {delete_spec} {ignore_spec} "{src_dir}" "{trg_dir}" """

        return sync_command

    def remove_file(self, file_to_remove):
        remove_command = f"""rm -f -v "{file_to_remove}" """
        return remove_command

    def remove_dir(self, dir_to_remove):
        remove_command = f"""rm -f -v -r "{dir_to_remove}" """
        return remove_command


class PlatformSpecificHelperBase(object):
    def __init__(self, instlObj) -> None:
        self.instlObj = instlObj
        self.copy_tool = None
        self.dl_tool = None
        self.num_items_for_progress_report = 0
        self.progress_staccato_period = config_vars.get("PROGRESS_STACCATO_PERIOD", "128").int()
        self.progress_staccato_count = 0
        self.no_progress_messages = False
        self.random_invocation_id = ''.join(random.choice(string.ascii_lowercase) for _ in range(16))

    def DefaultCopyToolName(self, target_os):
        if target_os == "Win":
            retVal = "robocopy"
        elif target_os == "Mac":
            retVal = "rsync"
        elif target_os == 'Linux':
            retVal = "rsync"
        else:
            raise ValueError(target_os, "has no valid default copy tool")
        return retVal

    @abc.abstractmethod
    def init_platform_tools(self):
        """ platform specific initialization of the download tool object.
            Can be done only after the definitions for index have been read."""
        pass

    def init_copy_tool(self):
        copy_tool_name = self.DefaultCopyToolName(config_vars["__CURRENT_OS__"].str()) # copy instructions are always produced for the current os
        if "COPY_TOOL" in config_vars:
            copy_tool_name = config_vars["COPY_TOOL"].str()
        self.use_copy_tool(copy_tool_name)

    @abc.abstractmethod
    def get_install_instructions_prefix(self, exit_on_errors=True):
        """ platform specific """
        pass

    @abc.abstractmethod
    def get_install_instructions_postfix(self):
        """ platform specific last lines of the install script """
        pass

    @abc.abstractmethod
    def mkdir(self, directory):
        """ platform specific mkdir """
        pass

    def mkdir_with_owner(self, directory, progress_num=0):
        return self.mkdir(directory)

    @abc.abstractmethod
    def cd(self, directory):
        """ platform specific cd """
        pass

    @abc.abstractmethod
    def pushd(self, directory):
        pass

    @abc.abstractmethod
    def popd(self):
        pass

    @abc.abstractmethod
    def save_dir(self, var_name):
        """ platform specific save current dir """
        pass

    @abc.abstractmethod
    def restore_dir(self, var_name):
        """ platform specific restore current dir """
        pass

    @abc.abstractmethod
    def rmdir(self, directory, recursive=False, check_exist=False):
        """ platform specific rmdir """
        pass

    @abc.abstractmethod
    def rmfile(self, a_file, quote_char='"', check_exist=False):
        """ platform specific rm file
        :param quote_char:
        """
        pass

    @abc.abstractmethod
    def rm_file_or_dir(self, file_or_dir):
        """ platform specific rm file or a dir """
        pass

    def new_line(self):
        return ""  # empty string because write_batch_file adds \n to each line

    def progress(self, msg, num_items=0):
        self.num_items_for_progress_report += num_items + 1
        if not self.no_progress_messages:
            prog_msg = f"Progress: {self.num_items_for_progress_report} of $(TOTAL_ITEMS_FOR_PROGRESS_REPORT); {msg}"
            return self.echo(prog_msg)
        else:
            return ()

    def progress_percent(self, msg, percent):
        """ create progress message and increase progress items by a percentage
        """
        inc_by = max(1, int(self.num_items_for_progress_report / 100) * int(percent))
        self.num_items_for_progress_report += inc_by
        if not self.no_progress_messages:
            prog_msg = f"Progress: {self.num_items_for_progress_report} of $(TOTAL_ITEMS_FOR_PROGRESS_REPORT); {msg}"
            return self.echo(prog_msg)
        else:
            return ()

    def progress_staccato(self, msg):
        retVal = ()
        self.progress_staccato_count = (self.progress_staccato_count + 1) % self.progress_staccato_period
        if self.progress_staccato_count == 0:
            retVal = self.progress(msg)
        return retVal

    def increment_progress(self, num_items=1):
        self.num_items_for_progress_report += num_items
        return self.num_items_for_progress_report

    @abc.abstractmethod
    def get_svn_folder_cleanup_instructions(self):
        """ platform specific cleanup of svn locks """
        pass

    @abc.abstractmethod
    def var_assign(self, identifier, value):
        pass

    def setup_echo(self):
        return ()

    @abc.abstractmethod
    def echo(self, message):
        pass

    @abc.abstractmethod
    def remark(self, remark):
        pass

    @abc.abstractmethod
    def use_copy_tool(self, tool):
        pass

    @abc.abstractmethod
    def copy_file_to_file(self, src_file, trg_file, hard_link=False, check_exist=False):
        """ Copy src_file to trg_file.
            Example: create_copy_file_to_file("a.txt", "/d/c/bt.txt") copies
            the file a.txt into "/d/c/bt.txt".
        """
        pass

    def svn_add_item(self, item_path):
        svn_command = " ".join(("$(SVN_CLIENT_PATH)", "add", '"' + item_path + '"'))
        return svn_command

    def svn_remove_item(self, item_path):
        svn_command = " ".join(("$(SVN_CLIENT_PATH)", "rm", "--force", '"' + item_path + '"'))
        return svn_command

    @abc.abstractmethod
    def check_checksum_for_file(self, a_file, checksum):
        pass

    def check_checksum_for_folder(self, info_map_file):
        check_checksum_for_folder_command = " ".join((self.run_instl(),
                                                      "check-checksum",
                                                      "--in", utils.quoteme_double(info_map_file),
                                                      "--start-progress", str(self.num_items_for_progress_report),
                                                      "--total-progress", "$(TOTAL_ITEMS_FOR_PROGRESS_REPORT)",
        ))
        return check_checksum_for_folder_command

    def create_folders(self, info_map_file):
        create_folders_command = " ".join((self.run_instl(),
                                           "create-folders",
                                           "--in", utils.quoteme_double(info_map_file),
                                           "--start-progress", str(self.num_items_for_progress_report),
                                           "--total-progress", "$(TOTAL_ITEMS_FOR_PROGRESS_REPORT)",
        ))
        return create_folders_command

    def set_exec_for_folder(self, info_map_file):
        set_exec_for_folder_command = " ".join((self.run_instl(),
                                                "set-exec",
                                                "--in", utils.quoteme_double(info_map_file),
                                                "--start-progress", str(self.num_items_for_progress_report),
                                                "--total-progress", "$(TOTAL_ITEMS_FOR_PROGRESS_REPORT)",
        ))
        return set_exec_for_folder_command

    def tar(self, to_tar_name):
        pass

    def unwtar_something(self, what_to_unwtar, no_artifacts=False, where_to_unwtar=None):
        unwtar_command_parts = [self.instlObj.platform_helper.run_instl(),
                                "unwtar",
                                "--in",
                                utils.quoteme_double(what_to_unwtar)]
        if no_artifacts:
            unwtar_command_parts.append("--no-artifacts")

        if where_to_unwtar:
            unwtar_command_parts.extend(["--out", utils.quoteme_double(where_to_unwtar)])

        unwtar_command = " ".join(unwtar_command_parts)
        return unwtar_command

    def unwtar_current_folder(self, no_artifacts=False, where_to_unwtar=None):
        unwtar_command = self.unwtar_something(".", no_artifacts, where_to_unwtar)
        return unwtar_command

    def run_instl_command_list(self, command_file_path, parallel=False):
        command_parts = [self.instlObj.platform_helper.run_instl(),
                         "command-list",
                         "--config-file",
                         utils.quoteme_double(command_file_path)]
        if parallel:
            command_parts.append("--parallel")
        instl_batch_command = " ".join(command_parts)
        return instl_batch_command

    @abc.abstractmethod
    def wait_for_child_processes(self):
        pass

    @abc.abstractmethod
    def chmod(self, new_mode, file_path):
        pass

    @abc.abstractmethod
    def make_executable(self, file_path):
        pass

    @abc.abstractmethod
    def unlock(self, file_path, recursive=False, ignore_errors=True):
        """ Remove the system's read-only flag, this is different from permissions.
            For changing permissions use chmod.
        """
        pass

    @abc.abstractmethod
    def touch(self, file_path):
        pass

    def run_instl(self):
        return '"$(__INSTL_EXE_PATH__)"'

    @abc.abstractmethod
    def append_file_to_file(self, source_file, target_file):
        pass

    # overridden only on windows, unix shell scripts have set -e to auto exit if any subprocess returns exit code != 0
    def exit_if_any_error(self):
        return ()

    @abc.abstractmethod
    def chown(self, user_id, group_id, target_path, recursive=False):
        pass

def PlatformSpecificHelperFactory(in_os, instlObj, use_python_batch=False):
    if use_python_batch:
        from . import platformSpecificHelper_Python
        retVal = platformSpecificHelper_Python.PlatformSpecificHelperPython(instlObj, in_os)
    elif in_os == "Mac":
        from . import platformSpecificHelper_Mac

        retVal = platformSpecificHelper_Mac.PlatformSpecificHelperMac(instlObj)
    elif in_os == "Win":
        from . import platformSpecificHelper_Win

        retVal = platformSpecificHelper_Win.PlatformSpecificHelperWin(instlObj)
    elif in_os == "Linux":
        from . import platformSpecificHelper_Linux

        retVal = platformSpecificHelper_Linux.PlatformSpecificHelperLinux(instlObj)
    else:
        raise ValueError(f"{in_os} has no PlatformSpecificHelper")
    return retVal


class DownloadToolBase(object, metaclass=abc.ABCMeta):
    """ Create download commands. Each function should be overridden to implement the download
        on specific platform using a specific copying tool. All functions return
        a list of commands, even if there is only one. This will allow to return
        multiple commands if needed.
    """
    curl_write_out_str = r'%{url_effective}, %{size_download} bytes, %{time_total} sec., %{speed_download} bps.\n'
    # for debugging:
    curl_extra_write_out_str = r'    num_connects:%{num_connects}, time_namelookup: %{time_namelookup}, time_connect: %{time_connect}, time_pretransfer: %{time_pretransfer}, time_redirect: %{time_redirect}, time_starttransfer: %{time_starttransfer}\n\n'

    def __init__(self, platform_helper) -> None:
        self.platform_helper = platform_helper
        self.urls_to_download = list()
        self.short_win_paths_cache = dict()

    @abc.abstractmethod
    def download_url_to_file(self, src_url, trg_file):
        pass

    def add_download_url(self, url, path, verbatim=False, size=0):
        if verbatim:
            translated_url = url
        else:
            translated_url = connectionBase.connection_factory().translate_url(url)
        self.urls_to_download.append((translated_url, path, size))

    def get_num_urls_to_download(self):
        return len(self.urls_to_download)

    def download_from_config_file(self, config_file):
        pass

    @abc.abstractmethod
    def download_from_config_files(self, parallel_run_config_file_path, config_files):
        pass

    def create_config_files(self, curl_config_file_path, num_config_files):
        file_name_list = list()
        num_urls_to_download = len(self.urls_to_download)
        if num_urls_to_download > 0:
            connect_time_out = str(config_vars.setdefault("CURL_CONNECT_TIMEOUT", "16"))
            max_time = str(config_vars.setdefault("CURL_MAX_TIME", "180"))
            retries = str(config_vars.setdefault("CURL_RETRIES", "2"))
            retry_delay = str(config_vars.setdefault("CURL_RETRY_DELAY", "8"))

            sync_urls_cookie = str(config_vars.get("COOKIE_FOR_SYNC_URLS", ""))

            actual_num_config_files = int(max(0, min(num_urls_to_download, num_config_files)))
            num_digits = len(str(actual_num_config_files))
            file_name_list = ["-".join((curl_config_file_path, str(file_i).zfill(num_digits))) for file_i in range(actual_num_config_files)]

            # open the files make sure they have r/w permissions and are utf-8
            wfd_list = list()
            for file_name in file_name_list:
                wfd = utils.utf8_open(file_name, "w")
                utils.make_open_file_read_write_for_all(wfd)
                wfd_list.append(wfd)

            # write the header in each file
            for wfd in wfd_list:
                basename = os.path.basename(wfd.name)
                if sync_urls_cookie:
                    cookie_text = f"cookie = {sync_urls_cookie}\n"
                else:
                    cookie_text = ""
                curl_write_out_str = DownloadToolBase.curl_write_out_str
                file_header_text = f"""
insecure
raw
fail
silent
show-error
compressed
create-dirs
connect-timeout = {connect_time_out}
max-time = {max_time}
retry = {retries}
retry-delay = {retry_delay}
{cookie_text}
write-out = "Progress: ... of ...; {basename}: {curl_write_out_str}


"""
                wfd.write(file_header_text)

            def url_sorter(l, r):
                """ smaller files should be downloaded first so the progress bar gets moving early.
                    However if Info.xml for direct sync is downloaded first and than some other file fails,
                    next time instl will not attempt to direct sync the folder again. So Info.xml
                    files are sorted last, although this does not guaranty to help with this situation
                    because the download is done in parallel. All we can do is make sure the Info.xml
                    is last in it's own curl config file"""
                if l[0].endswith('Info.xml'):
                    return sys.maxsize
                elif r[0].endswith('Info.xml'):
                    return -sys.maxsize
                else:
                    return l[2] - r[2]  # non Info.xml files are sorted by size

            wfd_cycler = itertools.cycle(wfd_list)
            url_num = 0
            sorted_by_size = sorted(self.urls_to_download, key=functools.cmp_to_key(url_sorter))
            if 'Win' in utils.get_current_os_names():
                import win32api
            for url, path, size in sorted_by_size:
                fixed_path = pathlib.PurePath(path)
                if 'Win' in utils.get_current_os_names():
                    # to overcome cUrl inability to handle path with unicode chars, we try to calculate the windows
                    # short path (DOS style 8.3 chars). The function that does that, win32api.GetShortPathName,
                    # does not work for paths that do not yet exist so we need to also create the folder.
                    # However if the creation requires admin permissions - it could fail -
                    # in which case we revert to using the long path.
                    fixed_path_parent = str(fixed_path.parent)
                    fixed_path_name = str(fixed_path.name)
                    if fixed_path_parent not in self.short_win_paths_cache:
                        try:
                            os.makedirs(fixed_path_parent, exist_ok=True)
                            short_parent_path = win32api.GetShortPathName(fixed_path_parent)
                            self.short_win_paths_cache[fixed_path_parent] = short_parent_path
                        except Exception as e:  # failed to mkdir or get the short path? never mind, just use the full path
                            self.short_win_paths_cache[fixed_path_parent] = fixed_path_parent
                            print("warning creating short path failed for", fixed_path, e, "using long path")

                    short_file_path = os.path.join(self.short_win_paths_cache[fixed_path_parent], fixed_path_name)
                    fixed_path = short_file_path.replace("\\", "\\\\")
                wfd = next(wfd_cycler)
                wfd.write(f'''url = "{url}"\noutput = "{fixed_path}"\n\n''')
                url_num += 1

            for wfd in wfd_list:
                wfd.close()

        return file_name_list
