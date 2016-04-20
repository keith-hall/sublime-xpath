import sublime
import sublime_plugin

class RequestInputCommand(sublime_plugin.TextCommand): # this command should be overidden, and not used directly
    on_query_completions_callbacks = dict()
    on_completion_committed_callbacks = dict()
    
    def run(self, edit, **args):
        self.input_panel = None
        self.pending_value = None
        self.current_value = None
        self.timeout_active = False
        self.set_args(**args)
        self.parse_args()
        
        self.show_input_panel(self.get_value_from_args('initial_value', ''))
    
    def show_input_panel(self, initial_value):
        self.input_panel = self.view.window().show_input_panel(self.get_value_from_args('label', ''), initial_value, self.input_done, self.input_changed, self.input_cancelled)
        self.input_panel.set_name('input_panel: ' + self.get_value_from_args('label', ''))
        syntax = self.get_value_from_args('syntax', None)
        if syntax is not None:
            self.input_panel.assign_syntax(syntax)
        self.input_panel.settings().set('gutter', False)
        self.input_panel.settings().set('highlight_line', False) # in case this bug is ever fixed: https://github.com/SublimeTextIssues/Core/issues/586
        
        RequestInputCommand.on_query_completions_callbacks[self.input_panel.id()] = lambda prefix, locations: self.on_query_completions(prefix, locations)
        RequestInputCommand.on_completion_committed_callbacks[self.input_panel.id()] = lambda: self.on_completion_committed()
    
    def set_args(self, **args):
        self.arguments = args or {}
    
    def parse_args(self):
        self.live_mode = self.get_value_from_args('live_mode', True)
    
    def get_value_from_args(self, key, default):
        if key in self.arguments:
            if self.arguments[key] is not None:
                return self.arguments[key]
        return default
    
    def close_input_panel(self):
        sublime.active_window().run_command('hide_panel', { 'cancel': True }) # close input panel
        #self.input_panel = None # not necessary as input_cancelled method is called
    
    def compare_to_previous(self):
        """Compare the pending_value with the current_value and process it if it is different."""
        self.timeout_active = False
        if self.pending_value != self.current_value: # no point reporting the same input again
            self.current_value = self.pending_value
            self.process_current_input()
    
    def input_changed(self, value):
        """When the input is changed in live mode, after a short delay (so that it doesn't report unnecessarily while the text is still being typed), report the current value.""" # TODO: consider having a "pending" report in non-live mode, so that, for example, the xpath query can still be validated while it is being typed?
        self.pending_value = value
        
        if self.live_mode:
            use_delay = self.get_value_from_args('delay', 0)
            if self.current_value is None: # if this is the initial input, report it immediately
                use_delay = 0
            
            if not self.timeout_active:
                self.timeout_active = True
                if self.get_value_from_args('async', True):
                    timeout = sublime.set_timeout_async
                else:
                    timeout = sublime.set_timeout
                timeout(lambda: self.compare_to_previous(), use_delay)
    
    def input_panel_closed(self):
        if self.input_panel is not None:
            RequestInputCommand.on_query_completions_callbacks.pop(self.input_panel.id(), None) # remove callback if present
            RequestInputCommand.on_completion_committed_callbacks.pop(self.input_panel.id(), None) # remove callback if present
        self.input_panel = None
    
    def input_cancelled(self):
        self.input_panel_closed()
    
    def input_done(self, value):
        """When input is completed, if the current value hasn't already been processed, process it now."""
        self.input_panel_closed()
        self.pending_value = value
        self.compare_to_previous()
    
    def process_current_input(self):
        pass
    
    def on_query_completions(self, prefix, locations): # http://docs.sublimetext.info/en/latest/reference/api.html#sublime_plugin.EventListener.on_query_completions
        pass
    
    def on_completion_committed(self):
        pass
    
    def refresh_selection_bug_work_around(self):
        # https://github.com/SublimeTextIssues/Core/issues/485
        # refresh_selection_bug_work_around() provides a workaround for the Sublime
        # Text bug whereby selections do not always get displayed correctly
        # immediately after being altered by a plugin.
        
        # Adding and then removing an empty list of regions in the view
        # ensures that all selections are refreshed and displayed correctly.
        # Using an actual list of regions say, self.view.sel(), also works.
        
        empty_list = []
        
        bug_reg_key = 'selection_bug_demo_workaround_regions_key'
        
        self.view.add_regions(bug_reg_key, empty_list, 'no_scope', '', sublime.HIDDEN)
        
        self.view.erase_regions(bug_reg_key)
        
    # End of def refreshSelectionBugWorkAround()

class InputCompletionsListener(sublime_plugin.EventListener):
    def __init__(self):
        self.previous_command = dict()
    
    def on_query_completions(self, view, prefix, locations):
        if view.id() in RequestInputCommand.on_query_completions_callbacks.keys():
            self.previous_command[view.id()] = 'auto_complete'
            return RequestInputCommand.on_query_completions_callbacks[view.id()](prefix, locations)
    
    def on_pre_close(self, view):
        RequestInputCommand.on_query_completions_callbacks.pop(view.id(), None) # remove callback if present
        self.previous_command[view.id()] = None
    
    def on_post_text_command(self, view, command_name, args):
        if view.id() in RequestInputCommand.on_completion_committed_callbacks.keys():
            self.previous_command[view.id()] = command_name
            if command_name in ('commit_completion', 'insert_best_completion'):
                RequestInputCommand.on_completion_committed_callbacks[view.id()]()
    
    def on_modified_async(self, view):
        if view.id() in RequestInputCommand.on_completion_committed_callbacks.keys():
            if self.previous_command.get(view.id(), None) == 'auto_complete': # detect when auto_complete was shown and the user clicked on an entry rather than pressing tab - https://forum.sublimetext.com/t/how-to-detect-commands-run-by-a-plugin-when-an-autocomplete-entry-is-clicked-on-by-the-mouse/19073
                self.on_post_text_command(view, 'commit_completion', None)
