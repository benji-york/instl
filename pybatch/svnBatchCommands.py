from typing import List
import re
import io
from configVar import config_vars
from db import DBManager
from .baseClasses import *
from .subprocessBatchCommands import RunProcessBase


class SVNClient(RunProcessBase, kwargs_defaults={"url": None, "depth": "infinity", "repo_rev": -1}):
    def __init__(self, command, **kwargs) -> None:
        super().__init__(**kwargs)
        self.command = command

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(utils.quoteme_single(self.command))

    def progress_msg_self(self) -> str:
        return f'''svn {self.command}'''

    def get_run_args(self, run_args) -> None:
        run_args.append(config_vars.get("SVN_CLIENT_PATH", "svn").str())
        run_args.append(self.command)
        if self.url_with_repo_rev():
            run_args.append(self.url_with_repo_rev())
        run_args.append("--depth")
        run_args.append(self.depth)

    def url_with_repo_rev(self):
        if self.repo_rev == -1:
            retVal = self.url
        else:
            retVal = f"{self.url}@{self.repo_rev}"
        return retVal


class SVNSetProp(SVNClient):
    def __init__(self, prop_name, prop_value, file_path, **kwargs) -> None:
        super().__init__('propset', **kwargs)
        self.prop_name = prop_name
        self.prop_value = prop_value
        self.file_path = file_path

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(self.unnamed__init__param(self.prop_name))
        all_args.append(self.unnamed__init__param(self.prop_value))
        all_args.append(self.unnamed__init__param(self.file_path))

    def progress_msg_self(self) -> str:
        return f'''svn {self.command} {self.prop_name} {self.prop_value} {self.file_path}'''

    def get_run_args(self, run_args) -> None:
        super().get_run_args(run_args)
        run_args.append(self.prop_name)
        run_args.append(self.prop_value)
        run_args.append(os.fspath(self.file_path))


class SVNDelProp(SVNClient):
    def __init__(self, prop_name, file_path, **kwargs) -> None:
        super().__init__('propdel', **kwargs)
        self.prop_name = prop_name
        self.file_path = file_path

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(self.unnamed__init__param(self.prop_name))
        all_args.append(self.unnamed__init__param(self.file_path))

    def progress_msg_self(self) -> str:
        return f'''svn {self.command} {self.prop_name} {self.file_path}'''

    def get_run_args(self, run_args) -> None:
        super().get_run_args(run_args)
        run_args.append(self.prop_name)
        run_args.append(os.fspath(self.file_path))


class SVNLastRepoRev(SVNClient, kwargs_defaults={"depth": "empty"}):
    """ get the last repository revision from a url to SVN repository
        the result is placed in a configVar
        :url_param: url to svn repository
        :reply_config_var: the name of the configVar where the last repository revision is placed
    """
    revision_line_re = re.compile("^Revision:\s+(?P<revision>\d+)$")

    def __init__(self, **kwargs):
        super().__init__("info", **kwargs)

    def repr_own_args(self, all_args: List[str]) -> None:
        pass

    def get_run_args(self, run_args) -> None:
        super().get_run_args(run_args)
        run_args.append(self.url)

    def handle_completed_process(self, completed_process):
        info_as_io = io.StringIO(utils.unicodify(completed_process.stdout))
        for line in info_as_io:
            match = self.revision_line_re.match(line)
            if match:
                last_repo_rev = int(match["revision"])
                break
        else:
            raise ValueError(f"Could not find last repo rev for {self.url}")
        if self.reply_config_var:
            config_vars[self.reply_config_var] = str(last_repo_rev)


class SVNCheckout(SVNClient):

    def __init__(self, where, **kwargs):
        super().__init__("checkout", **kwargs)
        self.where = where

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(self.named__init__param("where", os.fspath(self.where)))

    def get_run_args(self, run_args) -> None:
        super().get_run_args(run_args)
        run_args.append(self.where)


class SVNInfo(SVNClient):

    def __init__(self, **kwargs):
        super().__init__("info", **kwargs)

    def repr_own_args(self, all_args: List[str]) -> None:
        pass


class SVNPropList(SVNClient):

    def __init__(self, with_values=False, **kwargs):
        super().__init__("proplist", **kwargs)
        self.with_values = with_values

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(self.optional_named__init__param("with_values", self.with_values, False))

    def get_run_args(self, run_args) -> None:
        super().get_run_args(run_args)
        if self.with_values:
            run_args.append("--verbose")


class SVNAdd(SVNClient):

    def __init__(self, file_to_add, **kwargs):
        super().__init__("add", **kwargs)
        self.file_to_add = file_to_add

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(self.named__init__param("file_to_add", os.fspath(self.file_to_add)))

    def progress_msg_self(self) -> str:
        return f'''adding to svn {self.file_to_add}'''

    def get_run_args(self, run_args) -> None:
        run_args.append(config_vars.get("SVN_CLIENT_PATH", "svn").str())
        run_args.append(self.command)
        run_args.append(self.file_to_add)


class SVNRemove(SVNClient):

    def __init__(self, file_to_remove, **kwargs):
        super().__init__("rm", **kwargs)
        self.file_to_remove = file_to_remove

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(self.named__init__param("file_to_remove", os.fspath(self.file_to_remove)))

    def progress_msg_self(self) -> str:
        return f'''removing from svn {self.file_to_remove}'''

    def get_run_args(self, run_args) -> None:
        super().get_run_args(run_args)
        run_args.append(config_vars.get("SVN_CLIENT_PATH", "svn").str())
        run_args.append(self.command)
        run_args.append("--force")
        run_args.append(self.file_to_remove)


class SVNInfoReader(DBManager, PythonBatchCommandBase):
    """
    read a file created by SVNPropList,SVNInfo, file-sizes
    possible formats: "info", "text", "props", "file-sizes"
    self.format = format
    """
    def __init__(self, file_to_read, format='text', **kwargs):
        super().__init__(**kwargs)
        self.file_to_read = file_to_read
        self.format = format

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(self.unnamed__init__param(self.file_to_read))
        all_args.append(self.optional_named__init__param("format", self.format, 'text'))

    def progress_msg_self(self) -> str:
        return f'''reading {self.file_to_read}; format={self.format}'''

    def __call__(self, *args, **kwargs) -> None:
        PythonBatchCommandBase.__call__(self, *args, **kwargs)
        resolved_info_map_path = utils.ResolvedPath(self.file_to_read)
        self.info_map_table.read_from_file(resolved_info_map_path, a_format=self.format, disable_indexes_during_read=True)
