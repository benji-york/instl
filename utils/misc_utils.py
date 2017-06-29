#!/usr/bin/env python3


import sys
import os
import re
import hashlib
import base64
import collections
import subprocess
import numbers
import stat
import pathlib
from timeit import default_timer
from decimal import Decimal
import rsa
from functools import reduce
from itertools import repeat
import tarfile

import utils


def Is64Windows():
    return 'PROGRAMFILES(X86)' in os.environ


def Is32Windows():
    return not Is64Windows()


def GetProgramFiles32():
    if Is64Windows():
        return os.environ['PROGRAMFILES(X86)']
    else:
        return os.environ['PROGRAMFILES']


def GetProgramFiles64():
    if Is64Windows():
        return os.environ['PROGRAMW6432']
    else:
        return None


def get_current_os_names():
    retVal = None
    import platform
    current_os = platform.system()
    if current_os == 'Darwin':
        retVal = ('Mac',)
    elif current_os == 'Windows':
        if Is64Windows():
            retVal = ('Win', 'Win64')
        else:
            retVal = ('Win', 'Win32')
    elif current_os == 'Linux':
        retVal = ('Linux',)
    return retVal


class write_to_list(object):
    """ list that behaves like a file. For each call to write
        another item is added to the list.
    """
    def __init__(self):
        self.the_list = list()

    def write(self, text):
        self.the_list.append(text)

    def list(self):
        return self.the_list


class unique_list(list):
    """
    unique_list implements a list where all items are unique.
    Functionality can also be described as set with order.
    unique_list should behave as a python list except:
        - Adding items the end of the list (by append, extend) will do nothing if the
            item is already in the list.
        - Adding to the middle of the list (insert, __setitem__)
            will remove previous item with the same value - if any.
    """
    __slots__ = ('__attendance',)

    def __init__(self, initial_list=()):
        super().__init__()
        self.__attendance = set()
        self.extend(initial_list)

    def __setitem__(self, index, item):
        prev_item = self[index]
        if prev_item != item:
            if item in self.__attendance:
                prev_index_for_item = self.index(item)
                super().__setitem__(index, item)
                del self[prev_index_for_item]
                self.__attendance.add(item)
            else:
                super().__setitem__(index, item)
                self.__attendance.remove(prev_item)
                self.__attendance.add(item)

    def __delitem__(self, index):
        super().__delitem__(index)
        self.__attendance.remove(self[index])

    def __contains__(self, item):
        """ Overriding __contains__ is not required - just more efficient """
        return item in self.__attendance

    def append(self, item):
        if item not in self.__attendance:
            super().append(item)
            self.__attendance.add(item)

    def extend(self, items=()):
        for item in items:
            if item not in self.__attendance:
                super().append(item)
                self.__attendance.add(item)

    def insert(self, index, item):
        if item in self.__attendance:
            prev_index_for_item = self.index(item)
            if index != prev_index_for_item:
                super().insert(index, item)
                if prev_index_for_item < index:
                    super().__delitem__(prev_index_for_item)
                else:
                    super().__delitem__(prev_index_for_item+1)
        else:
            super().insert(index, item)
            self.__attendance.add(item)

    def remove(self, item):
        if item in self.__attendance:
            super().remove(item)
            self.__attendance.remove(item)

    def pop(self, index=-1):
        self.__attendance.remove(self[index])
        return super().pop(index)

    def count(self, item):
        """ Overriding count is not required - just more efficient """
        return 1 if item in self.__attendance else 0

    def sort(self, key=None, reverse=False):
        """ Sometimes sort is needed after all ... """
        super().sort(key=key, reverse=reverse)

    def empty(self):
        return len(self.__attendance) == 0

    def clear(self):
        super().clear()
        self.__attendance.clear()


class set_with_order(unique_list):
    """ Just another name for unique_list """
    def __init__(self, initial_list=()):
        super().__init__(initial_list)


# noinspection PyProtectedMember
def print_var(var_name):
    calling_frame = sys._getframe().f_back
    var_val = calling_frame.f_locals.get(var_name, calling_frame.f_globals.get(var_name, None))
    print(var_name+':', str(var_val))


def deprecated(deprecated_func):
    def raise_deprecation(*unused_args, **unused_kwargs):
        del unused_args, unused_kwargs
        raise DeprecationWarning(deprecated_func.__name__, "is deprecated")

    return raise_deprecation


def max_widths(list_of_lists):
    """ inputs is a list of lists. output is a list of maximum str length for each
        position. E.g (('a', 'ccc'), ('bb', a', 'fff')) will return: (2, 3, 3)
    """
    longest_list_len = reduce(max, [len(a_list) for a_list in list_of_lists], 0)
    width_list = [0] * longest_list_len  # pre allocate the max list length
    align_list = ['<'] * longest_list_len  # default is align to left
    for a_list in list_of_lists:
        for item in enumerate(a_list):
            width_list[item[0]] = max(width_list[item[0]], len(str(item[1])))
            if isinstance(item[1], numbers.Number):
                align_list[item[0]] = '>'
    return width_list, align_list


def gen_col_format(width_list, align_list=None, sep=' '):
    """ generate a list of format string where each position is aligned to the adjacent
        position in the width_list.
        If align_list is supplied we can align numbers to the right and texts to the left
    """
    if align_list is None:
        align_list = ['<'] * len(width_list)

    format_list = list()

    for width_enum in enumerate(width_list):
        format_list.append("{{:{align}{width}}}".format(width=width_enum[1], align=align_list[width_enum[0]]))

    retVal = list()
    retVal.append("")  # for formatting a list of len 0
    for i in range(1, len(format_list)+1):
        retVal.append(sep.join(format_list[0:i]))
    return retVal


def ContinuationIter(the_iter, continuation_value=None):
    """ ContinuationIter yield all the values of the_iter and then continue yielding continuation_value
    """
    yield from the_iter
    yield from repeat(continuation_value)


def ParallelContinuationIter(*iterables):
    """ Like zip ParallelContinuationIter will yield a list of items from the
        same positions in the lists in iterables. If list are not of the same size
        None will be produced
        ParallelContinuationIter([1, 2, 3], ["a", "b"]) will yield:
        [1, "a"]
        [2, "b"]
        [3, None]
    """
    max_size = max([len(lis) for lis in iterables])
    continue_iterables = list(map(ContinuationIter, iterables))
    for i in range(max_size):
        yield list(map(next, continue_iterables))


def create_file_signatures(file_path, private_key_text=None):
    """ create rsa signature and sha1 checksum for a file.
        return a dict with "SHA-512_rsa_sig" and "sha1_checksum" entries.
    """
    retVal = dict()
    with open(file_path, "rb") as rfd:
        file_contents = rfd.read()
        sha1ner = hashlib.sha1()
        sha1ner.update(file_contents)
        checksum = sha1ner.hexdigest()
        retVal["sha1_checksum"] = checksum
        if private_key_text is not None:
            private_key_obj = rsa.PrivateKey.load_pkcs1(private_key_text, format='PEM')
            binary_sig = rsa.sign(file_contents, private_key_obj, 'SHA-512')
            text_sig = base64.b64encode(binary_sig)
            retVal["SHA-512_rsa_sig"] = text_sig
    return retVal


def get_buffer_checksum(buff):
    sha1ner = hashlib.sha1()
    sha1ner.update(buff)
    retVal = sha1ner.hexdigest()
    return retVal


def compare_checksums(_1st_checksum, _2nd_checksum):
    retVal = _1st_checksum.lower() == _2nd_checksum.lower()
    return retVal


def check_buffer_checksum(buff, expected_checksum):
    checksum = get_buffer_checksum(buff)
    retVal = compare_checksums(checksum, expected_checksum)
    return retVal


def check_buffer_signature(buff, textual_sig, public_key):
    try:
        pubkeyObj = rsa.PublicKey.load_pkcs1(public_key, format='PEM')
        binary_sig = base64.b64decode(textual_sig)
        rsa.verify(buff, binary_sig, pubkeyObj)
        return True
    except Exception:
        return False


def check_buffer_signature_or_checksum(buff, public_key=None, textual_sig=None, expected_checksum=None):
    retVal = False
    if public_key and textual_sig:
        retVal = check_buffer_signature(buff, textual_sig, public_key)
    elif expected_checksum:
        retVal = check_buffer_checksum(buff, expected_checksum)
    return retVal


def check_file_signature_or_checksum(file_path, public_key=None, textual_sig=None, expected_checksum=None):
    with open(file_path, "rb") as rfd:
        retVal = check_buffer_signature_or_checksum(rfd.read(), public_key, textual_sig, expected_checksum)
    return retVal


def check_file_checksum(file_path, expected_checksum):
    retVal = False  # if file does not exist return False
    try:
        with open(file_path, "rb") as rfd:
            retVal = check_buffer_checksum(rfd.read(), expected_checksum)
    except:
        pass
    return retVal


def get_file_checksum(file_path, follow_symlinks=True):
    """ return the sha1 checksum of the contents of a file.
        If file_path is a symbolic link and follow_symlinks is True
            the file pointed by the symlink is checksumed.
        If file_path is a symbolic link and follow_symlinks is False
            the contents of the symlink is checksumed - by calling os.readlink.
    """
    if os.path.islink(file_path) and not follow_symlinks:
        retVal = get_buffer_checksum(os.readlink(file_path).encode())
    else:
        with open(file_path, "rb") as rfd:
            retVal = get_buffer_checksum(rfd.read())
    return retVal


def check_file_signature(file_path, textual_sig, public_key):
    with open(file_path, "rb") as rfd:
        retVal = check_buffer_signature(rfd.read(), textual_sig, public_key)
    return retVal


def need_to_download_file(file_path, file_checksum):
    retVal = True
    if os.path.isfile(file_path):
        retVal = not check_file_checksum(file_path, file_checksum)
    return retVal


def quoteme_single(to_quote):
    return "".join(("'", to_quote, "'"))


def quoteme_single_list(to_quote_list, ):
    return [quoteme_single(to_q) for to_q in to_quote_list]


def quoteme_double(to_quote):
    return "".join(('"', to_quote, '"'))


def quoteme_double_list(to_quote_list, ):
    return [quoteme_double(to_q) for to_q in to_quote_list]

detect_quotations = re.compile("(?P<prefix>[\"'])(?P<the_unquoted_text>.+)(?P=prefix)")


def unquoteme(to_unquote):
    retVal = to_unquote
    has_quotations = detect_quotations.match(to_unquote)
    if has_quotations:
        retVal = has_quotations.group('the_unquoted_text')
    return retVal

guid_re = re.compile("""
                [a-f0-9]{8}
                (-[a-f0-9]{4}){3}
                -[a-f0-9]{12}
                $
                """, re.VERBOSE)


def separate_guids_from_iids(items_list):
    reVal_non_guids = list()
    retVal_guids = list()
    for item in items_list:
        if guid_re.match(item.lower()):
            retVal_guids.append(item.lower())
        else:
            reVal_non_guids.append(item)
    return reVal_non_guids, retVal_guids


def make_one_list(*things):
    """ flatten things to one single list.
    """
    retVal = list()
    for thing in things:
        if isinstance(thing, collections.Iterable) and not isinstance(thing, str):
            retVal.extend(thing)
        else:
            retVal.append(thing)
    return retVal


def P4GetPathFromDepotPath(depot_path):
    retVal = None
    command_parts = ["p4", "where", depot_path]
    p4_process = subprocess.Popen(command_parts, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    _stdout, _stderr = p4_process.communicate()
    _stdout, _stderr = unicodify(_stdout), unicodify(_stderr)
    return_code = p4_process.returncode
    if return_code == 0:
        lines = _stdout.split("\n")
        where_line_reg_str = "".join((re.escape(depot_path), "\s+", "//.+", "\s+", "(?P<disk_path>/.+)"))
        match = re.match(where_line_reg_str, lines[0])
        if match:
            retVal = match.group('disk_path')
            if retVal.endswith("/..."):
                retVal = retVal[0:-4]
    return retVal


def replace_all_from_dict(in_text, *in_replace_only_these, **in_replacement_dic):
    """ replace all occurrences of the values in in_replace_only_these
        with the values in in_replacement_dic. If in_replace_only_these is empty
        use in_replacement_dic.keys() as the list of values to replace."""
    retVal = in_text
    if not in_replace_only_these:
        # use the keys of of the replacement_dic as replace_only_these
        in_replace_only_these = list(in_replacement_dic.keys())[:]
    # sort the list by size (longer first) so longer string will be replace before their shorter sub strings
    for look_for in sorted(in_replace_only_these, key=lambda s: -len(s)):
        retVal = retVal.replace(look_for, in_replacement_dic[look_for])
    return retVal


# find sequences in a sorted list.
# in_sorted_list: a sorted list of things to search sequences in.
# is_next_func: The function that determines if one thing is the consecutive of another.
#               The default is to compare as integers.
# return_string: If true (the default) return a string in the format: "1-3, 4-5, 6, 8-9"
#                If false return a list of sequences
def find_sequences(in_sorted_list, is_next_func=lambda a, b: int(a)+1 == int(b), return_string=True):
    sequences = [[in_sorted_list[0]]]

    for item in in_sorted_list[1:]:
        if is_next_func(sequences[-1][-1], item):
            sequences[-1].append(item)
        else:
            sequences.append([item])

    if return_string:
        sequence_strings = []
        for sequence in sequences:
            if len(sequence) == 1:
                sequence_strings.append(str(sequence[0]))
            else:
                sequence_strings.append(str(sequence[0])+"-"+str(sequence[-1]))
        retVal = ", ".join(sequence_strings)
        return retVal
    else:
        return sequences


def timing(f):
    import time

    def wrap(*args, **kwargs):
        time1 = time.clock()
        ret = f(*args, **kwargs)
        time2 = time.clock()
        if time1 != time2:
            print('%s function took %0.3f ms' % (f.__name__, (time2-time1)*1000.0))
        else:
            print('%s function took apparently no time at all' % f.__name__)
        return ret
    return wrap


# compile a list of regexs to one regex. regexs are ORed
# with the | character so if any regex return true when calling
# re.search or of re.match the whole regex will return true.
def compile_regex_list_ORed(regex_list, verbose=False):
    combined_regex = "(" + ")|(".join(regex_list) + ")"
    if verbose:
        retVal = re.compile(combined_regex, re.VERBOSE)
    else:
        retVal = re.compile(combined_regex)
    return retVal


oct_digit_to_perm_chars = {'7': 'rwx', '6': 'rw-', '5': 'r-x', '4': 'r--', '3': '-wx', '2': '-w-', '1': '--x', '0': '---'}


def unix_permissions_to_str(the_mod):
    # python3: use stat.filemode for the permissions string
    prefix = '-'
    if stat.S_ISDIR(the_mod):
        prefix = 'd'
    elif stat.S_ISLNK(the_mod):
        prefix = 'l'
    oct_perm = oct(the_mod)[-3:]
    retVal = ''.join([prefix] + [oct_digit_to_perm_chars[p] for p in oct_perm])
    return retVal


def unicodify(in_something, encoding='utf-8'):
    if in_something is not None:
        if isinstance(in_something, str):
            retVal = in_something
        elif isinstance(in_something, bytes):
            retVal = in_something.decode(encoding)
        else:
            retVal = str(in_something)
    else:
        retVal = None
    return retVal


def bool_int_to_str(in_bool_int):
    if in_bool_int == 0:
        retVal = "no"
    else:
        retVal = "yes"
    return retVal


def str_to_bool_int(the_str):
    if the_str.lower() in ("yes", "true", "y", 't'):
        retVal = 1
    elif the_str.lower() in ("no", "false", "n", "f"):
        retVal = 0
    else:
        raise ValueError("Cannot translate", the_str, "to bool-int")
    return retVal


def str_to_bool(the_str, default=False):
    retVal = default
    if the_str.lower() in ("yes", "true", "y", 't'):
        retVal = True
    elif the_str.lower() in ("no", "false", "n", "f"):
        retVal = False
    return retVal


def is_iterable_but_not_str(obj_to_check):
    retVal = hasattr(obj_to_check, '__iter__') and not isinstance(obj_to_check, str)
    return retVal


class DictDiffer(object):
    """
    Calculate the difference between two dictionaries as:
    (1) items added
    (2) items removed
    (3) keys same in both but changed values
    (4) keys same in both and unchanged values
    """
    def __init__(self, current_dict, past_dict):
        self.current_dict, self.past_dict = current_dict, past_dict
        self.set_current, self.set_past = set(current_dict.keys()), set(past_dict.keys())
        self.intersect = self.set_current.intersection(self.set_past)

    def added(self):
        return self.set_current - self.intersect

    def removed(self):
        return self.set_past - self.intersect

    def changed(self):
        return set(o for o in self.intersect if sorted(self.past_dict[o]) != sorted(self.current_dict[o]))

    def unchanged(self):
        return set(o for o in self.intersect if sorted(self.past_dict[o]) == sorted(self.current_dict[o]))


def find_mount_point(path):
    mount_p = pathlib.PurePath(path)
    while not os.path.ismount(str(mount_p)):
        mount_p = mount_p.parent
    return str(mount_p)


class Timer_CM(object):
    def __init__(self, name, print_results=True):
        self.elapsed = Decimal()
        self._name = name
        self._print_results = print_results
        self._start_time = None
        self._children = {}

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()
        if self._print_results:
            self.print_results()

    def child(self, name):
        try:
            return self._children[name]
        except KeyError:
            result = Timer_CM(name, print_results=False)
            self._children[name] = result
            return result

    def start(self):
        self._start_time = self._get_time()

    def stop(self):
        self.elapsed += self._get_time() - self._start_time

    def print_results(self):
        print(self._format_results())

    def _format_results(self, indent='  '):
        result = '%s: %.3fs' % (self._name, self.elapsed)
        children = self._children.values()
        for child in sorted(children, key=lambda c: c.elapsed, reverse=True):
            child_lines = child._format_results(indent).split('\n')
            child_percent = child.elapsed / self.elapsed * 100
            child_lines[0] += ' (%d%%)' % child_percent
            for line in child_lines:
                result += '\n' + indent + line
        return result

    def _get_time(self):
        return Decimal(default_timer())


wtar_file_re = re.compile("""
    (?P<base_name>.+?)
    (?P<wtar_extension>\.wtar)
    (?P<split_numerator>\.[a-z]{2})?$""",
                          re.VERBOSE)


def is_wtar_file(in_possible_wtar):
    match = wtar_file_re.match(in_possible_wtar)
    retVal = match is not None
    return retVal


def is_first_wtar_file(in_possible_wtar):
    retVal = False
    match = wtar_file_re.match(in_possible_wtar)
    if match:
        split_numerator = match.group('split_numerator')
        retVal = split_numerator is None or split_numerator == ".aa"
    return retVal


# Given a name remove the trailing wtar or wtar.?? if any
# E.g. "a" => "a", "a.wtar" => "a", "a.wtar.aa" => "a"
def original_name_from_wtar_name(wtar_name):
    retVal = wtar_name
    match = wtar_file_re.match(wtar_name)
    if match:
        retVal = match.group('base_name')
    return retVal


# Given a list of file/folder names, replace those which are wtarred with the original file name.
# E.g. ['a', 'b.wtar', 'c.wtar.aa', 'c.wtar.ab'] => ['a', 'b', 'c']
# We must work on the whole list since several wtar file names might merge to a single original file name.
def original_names_from_wtars_names(original_list):
    replaced_list = unique_list()
    replaced_list.extend([original_name_from_wtar_name(file_name) for file_name in original_list])
    return replaced_list


def get_recursive_checksums(some_path, ignore=None):
    """ If some_path is a file return a dict mapping the file's path to it's sha1 checksum
        and mapping "total_checksum" to the files checksum, e.g.
        assuming /a/b/c.txt is a file
            get_recursive_checksums("/a/b/c.txt")
        will return: {c.txt: 1bc...aed, total_checksum: ed4...f4e}
        
        If some_path is a folder recursively walk the folder and return a dict mapping each file to it's sha1 checksum.
        and mapping "total_checksum" to a checksum of all the files checksums. 
        
        total_checksum is calculated by concatenating two lists:
         - list of all the individual file checksums
         - list of all individual paths paths
        The combined list is sorted and all members are concatenated into one string.
        The sha1 checksum of that string is the total_checksum
        Sorting is done to ensure same total_checksum is returned regardless the order
        in which os.scandir returned the files, but that a different checksum will be
        returned if a file changed it's name without changing contents.
        Note:
            - If you have a file called total_checksum your'e f**d.
            - Symlinks are not followed and are checksum as regular files (by calling readlink).
    """
    if ignore is None:
        ignore = ()
    retVal = dict()
    some_path_dir, some_path_leaf = os.path.split(some_path)
    if some_path_leaf not in ignore:
        if os.path.isfile(some_path):
                retVal[some_path_leaf] = get_file_checksum(some_path, follow_symlinks=False)
        elif os.path.isdir(some_path):
            for item in utils.scandir_walk(some_path, report_dirs=False):
                item_path_dir, item_path_leaf = os.path.split(item.path)
                if item_path_leaf not in ignore:
                    the_checksum = get_file_checksum(item.path, follow_symlinks=False)
                    normalized_path = pathlib.PurePath(item.path).as_posix()
                    retVal[normalized_path] = the_checksum

        checksum_list = sorted(list(retVal.keys()) + list(retVal.values()))
        string_of_checksums = "".join(checksum_list)
        retVal['total_checksum'] = get_buffer_checksum(string_of_checksums.encode())
    return retVal


def unwtar_a_file(wtar_file_path, destination_folder=None, no_artifacts=False, ignore=None):
    try:
        wtar_file_paths = utils.find_split_files(wtar_file_path)

        if destination_folder is None:
            destination_folder, _ = os.path.split(wtar_file_paths[0])
        print("unwtar", wtar_file_path, " to ", destination_folder)
        if ignore is None:
            ignore = ()

        first_wtar_file_dir, first_wtar_file_name = os.path.split(wtar_file_paths[0])
        destination_leaf_name = original_name_from_wtar_name(first_wtar_file_name)
        destination_path = os.path.join(destination_folder, destination_leaf_name)

        do_the_unwtarring = True
        with utils.MultiFileReader("br", wtar_file_paths) as fd:
            with tarfile.open(fileobj=fd) as tar:
                tar_total_checksum = tar.pax_headers.get("total_checksum")
                if tar_total_checksum:
                    if os.path.exists(destination_path):
                        disk_total_checksum = "disk_total_checksum_was_not_found"
                        with utils.ChangeDirIfExists(destination_folder):
                            disk_total_checksum = get_recursive_checksums(destination_leaf_name, ignore=ignore).get("total_checksum", "disk_total_checksum_was_not_found")

                        if disk_total_checksum == tar_total_checksum:
                            do_the_unwtarring = False
                            print(wtar_file_paths[0], "skipping unwtarring because item exists and is identical to archive")
                if do_the_unwtarring:
                    utils.safe_remove_file_system_object(destination_path)
                    tar.extractall(destination_folder)

        if no_artifacts:
            for wtar_file in wtar_file_paths:
                os.remove(wtar_file)

    except OSError as e:
        print("Invalid stream on split file with {}".format(wtar_file_paths[0]))
        raise e

    except tarfile.TarError:
        print("tarfile error while opening file", os.path.abspath(wtar_file_paths[0]))
        raise