import os
import shutil
from pathlib import Path
from typing import List
import logging
import utils
from pybatch import PythonBatchCommandBase

log = logging.getLogger()


class RmFile(PythonBatchCommandBase, essential=True):
    """remove a file
    - if path is symlink - the symlink's target will be removed
    - It's OK is the file does not exist
    - but exception will be raised if path is a folder
    """
    def __init__(self, path: os.PathLike, **kwargs) -> None:
        super().__init__(**kwargs)
        self.path: os.PathLike = path
        self.exceptions_to_ignore.append(FileNotFoundError)

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(utils.quoteme_raw_by_type(self.path))

    def progress_msg_self(self):
        return f"""Remove file '{self.path}'"""

    def __call__(self, *args, **kwargs):
        resolved_path = utils.ResolvedPath(self.path)
        if resolved_path.exists():
            self.doing = f"""removing file '{resolved_path}'"""
            resolved_path.unlink()


class RmDir(PythonBatchCommandBase, essential=True):
    """ remove a directory.
        - it's OK if the directory does not exist.
        - all files and directory under path will be removed recursively
        - exception will be raised if the path is not a folder
    """
    def __init__(self, path: os.PathLike, **kwargs) -> None:
        super().__init__(**kwargs)
        self.path: os.PathLike = path
        self.exceptions_to_ignore.append(FileNotFoundError)

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(utils.quoteme_raw_by_type(self.path))

    def progress_msg_self(self):
        return f"""Remove directory '{self.path}'"""

    def __call__(self, *args, **kwargs):
        resolved_path = utils.ResolvedPath(self.path)
        if resolved_path.exists():
            self.doing = f"""removing folder '{resolved_path}'"""
            shutil.rmtree(resolved_path)


class RmFileOrDir(PythonBatchCommandBase, essential=True):
    """ remove a file or directory.
    - it's OK if the path does not exist.
    - all files and directory under path will be removed recursively
    """
    def __init__(self, path: os.PathLike, **kwargs):
        super().__init__(**kwargs)
        self.path: os.PathLike = path
        self.exceptions_to_ignore.append(FileNotFoundError)

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(utils.quoteme_raw_by_type(self.path))

    def progress_msg_self(self):
        return f"""Remove '{self.path}'"""

    def __call__(self, *args, **kwargs):
        resolved_path = utils.ResolvedPath(self.path)
        if resolved_path.is_file():
            self.doing = f"""removing file'{resolved_path}'"""
            resolved_path.unlink()
        elif resolved_path.is_dir():
            self.doing = f"""removing folder'{resolved_path}'"""
            shutil.rmtree(resolved_path)


class RemoveEmptyFolders(PythonBatchCommandBase, essential=True, kwargs_defaults={"files_to_ignore": []}):
    """ remove all empty directories under and including 'folder_to_remove'
    - it's OK if the path does not exist.
    - 'files_to_ignore' is a list of file names will be ignored, i.e. if a folder contains only these files
    it will be considered empty and will be removed
    """
    def __init__(self, folder_to_remove: os.PathLike, **kwargs) -> None:
        super().__init__(**kwargs)
        self.folder_to_remove = folder_to_remove

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(f'''{utils.quoteme_raw_by_type(self.folder_to_remove)}''')

    def progress_msg_self(self) -> str:
        return f"""Remove empty directory '{self.folder_to_remove}'"""

    def __call__(self, *args, **kwargs) -> None:
        resolved_folder_to_remove = utils.ResolvedPath(self.folder_to_remove)
        for root_path, dir_names, file_names in os.walk(resolved_folder_to_remove, topdown=False, onerror=None, followlinks=False):
            # when topdown=False os.walk creates dir_names for each root_path at the beginning and has
            # no knowledge if a directory has already been deleted.
            existing_dirs = [dir_name for dir_name in dir_names if os.path.isdir(os.path.join(root_path, dir_name))]
            if len(existing_dirs) == 0:
                ignored_files = list()
                for filename in file_names:
                    if filename in self.files_to_ignore:
                        ignored_files.append(filename)
                    else:
                        break
                if len(file_names) == len(ignored_files):
                    # only remove the ignored files if the folder is to be removed
                    for filename in ignored_files:
                        file_to_remove_full_path = os.path.join(root_path, filename)
                        try:
                            self.doing = f"""removing ignored file '{file_to_remove_full_path}'"""
                            os.remove(file_to_remove_full_path)
                        except Exception as ex:
                            log.warning(f"""failed to remove {file_to_remove_full_path}, {ex}""")
                    try:
                        self.doing = f"""removing empty folder '{root_path}'"""
                        os.rmdir(root_path)
                    except Exception as ex:
                        log.warning(f"""failed to remove {root_path}, {ex}""")


class RmGlob(PythonBatchCommandBase, essential=True):
    """ remove files matching a pattern
        - it's OK if the directory does not exist.
        - all files and folders matching the pattern will be removed
        - pattern matching is done with https://docs.python.org/3.6/library/pathlib.html#pathlib.Path.glob
        - allowing pattern to be None is temporary until new format is implemented in index
"""
    def __init__(self, path_to_folder: os.PathLike, pattern: str=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.path_to_folder: os.PathLike = path_to_folder
        self.pattern: os.PathLike = pattern
        self.exceptions_to_ignore.append(FileNotFoundError)

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(utils.quoteme_raw_by_type(self.path_to_folder))
        all_args.append(utils.quoteme_raw_by_type(self.pattern))

    def progress_msg_self(self):
        return f"""Remove pattern '{self.pattern}' from {self.path_to_folder}"""

    def __call__(self, *args, **kwargs):
        if self.pattern is None:
            log.wanging(f"skip RmGlob of '{self.path_to_folder}' because pattern is None")
        else:
            folder = utils.ResolvedPath(self.path_to_folder)
            list_to_remove = folder.glob(self.pattern)
            for item in list_to_remove:
                with RmFileOrDir(item, own_progress_count=0) as rfod:
                    rfod()


class RmGlobs(PythonBatchCommandBase, essential=True):
    """ remove files matching any pattern in the given list
        - it's OK if the directory does not exist.
        - all files and folders matching the patterns will be removed
        - pattern matching is done with https://docs.python.org/3.6/library/pathlib.html#pathlib.Path.glob
        - allowing pattern to be None is temporary until new format is implemented in index
"""
    def __init__(self, path_to_folder: os.PathLike, *patterns: List, **kwargs) -> None:
        super().__init__(**kwargs)
        self.path_to_folder: os.PathLike = path_to_folder
        self.patterns = sorted(patterns)
        self.exceptions_to_ignore.append(FileNotFoundError)

    def repr_own_args(self, all_args: List[str]) -> None:
        all_args.append(utils.quoteme_raw_by_type(self.path_to_folder))
        for pattern in self.patterns:
            all_args.append(utils.quoteme_raw_by_type(pattern))

    def progress_msg_self(self):
        return f"""Remove patterns '{self.patterns}' from {self.path_to_folder}"""

    def __call__(self, *args, **kwargs):
        folder = utils.ResolvedPath(self.path_to_folder)
        for pattern in self.patterns:
            list_to_remove = folder.glob(pattern)
            for item in list_to_remove:
                with RmFileOrDir(item, own_progress_count=0) as rfod:
                    rfod()


# todo: class EmptyDir that will remove all contents from dir
