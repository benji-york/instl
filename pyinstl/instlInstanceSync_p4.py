#!/usr/bin/env python3


from .instlInstanceSyncBase import InstlInstanceSync
from configVar import var_stack


class InstlInstanceSync_p4(InstlInstanceSync):
    """  Class to create sync instruction using static links.
    """

    def __init__(self, instlObj):
        super().__init__(instlObj)

    def init_sync_vars(self):
        super().init_sync_vars()

    def create_sync_instructions(self):
        super().create_sync_instructions()
        self.create_download_instructions()
        self.instlObj.batch_accum.set_current_section('post-sync')

    def create_download_instructions(self):
        self.instlObj.batch_accum.set_current_section('sync')
        self.instlObj.batch_accum += self.instlObj.platform_helper.progress("Starting sync from $(SYNC_BASE_URL)")
        self.sync_base_url = var_stack.ResolveVarToStr("SYNC_BASE_URL")

        self.instlObj.batch_accum += self.instlObj.platform_helper.new_line()

        for iid in var_stack.ResolveVarToList("__FULL_LIST_OF_INSTALL_TARGETS__"):
            with self.install_definitions_index[iid].push_var_stack_scope():
                for source_var in var_stack.get_configVar_obj("iid_source_var_list"):
                    source = var_stack.ResolveVarToList(source_var)
                    self.p4_sync_for_source(source)

    def p4_sync_for_source(self, source):
        """ source is a tuple (source_folder, tag), where tag is either !file or !dir """
        source_path, source_type = source[0], source[1]
        if source_type == '!file':
            self.instlObj.batch_accum += " ".join(("p4", "sync", '"$(SYNC_BASE_URL)/' + source_path + '"$(REPO_REV)'))
        elif source_type == '!dir' or source_type == '!dir_cont':  # !dir and !dir_cont are only different when copying
            self.instlObj.batch_accum += " ".join(("p4", "sync", '"$(SYNC_BASE_URL)/' + source_path + '/..."$(REPO_REV)'))
