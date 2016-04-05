import sublime
import sublime_plugin
import os
from uuid import uuid4 as guid

class ValidatedSettings:
    registered_settings = dict()
    
    @staticmethod
    def load(base_name):
        if base_name in ValidatedSettings.registered_settings:
            return ValidatedSettings.registered_settings[base_name]
        else:
            settings = ValidatedSettings()
            settings.base_file_name = base_name
            settings.base = sublime.load_settings(base_name)
            ValidatedSettings.registered_settings[base_name] = settings
            settings.id = str(guid())
            settings.add_on_change(settings.id, settings.validate_all)
            
            return settings
    
    def unload(self):
        self.clear_on_change(self.id)
        ValidatedSettings.registered_settings.pop(self.base_file_name)
    
    def save(self):
        """Updates the settings file on the disk."""
        sublime.save_settings(self.base_file_name)
    
    def get(self, name):
        """Returns the value of the named setting."""
        value = self.base.get(name)
        try:
            self.validate_key_value_pair(name, value)
        except ValueError as e:
            print('Error reading settings file "' + self.base_file_name + '": ' + repr(e))
            # get the default value
            path = sublime.find_resources(self.base_file_name)[0] # index 0 is always the file shipped with the package. index 1 would be the User file.
            defaults = sublime.decode_value(sublime.load_resource(path))
            value = defaults[name]
            self.validate_key_value_pair(name, value)
        return value
    
    def get_from_args_then_settings(self, key, args):
        """Retrieve the value for the given key from the args if it is present, otherwise from the user settings if it is present, otherwise use value in the default settings."""
        get_from_settings = False
        value = None
        if args is not None and key in args:
            value = args[key]
            try:
                self.validate_key_value_pair(key, value)
            except ValueError as e:
                print('Error parsing arg that has the same behavior as a key in settings file "' + self.base_file_name + '": ' + repr(e))
                get_from_settings = True
        else:
            get_from_settings = True
        if get_from_settings:
            value = self.get(key)
        return value
    
    # def get(self, name, default):
    #     value = self.base.get(name, default)
    #     self.validate_key_value_pair(name, value)
    #     return value
    
    def set(self, name, value):
        """Sets the named setting if it is valid. Only primitive types, lists, and dictionaries are accepted."""
        self.validate_key_value_pair(name, value)
        old_value = None
        try:
            old_value = self.get(name)
        except:
            pass
        self.base.set(name, value)
        if old_value != value:
            pass # TODO: call any relevant callbacks
    
    def erase(self, name):
        """Removes the named setting. Does not remove it from any parent Settings."""
        self.base.erase(name)
    
    def has(self, name):
        """Returns true if the named option exists in this set of Settings or one of its parents."""
        return self.base.has(name)
    
    def add_on_change(self, callback_id, on_change):
        """Register a callback to be run whenever any settings in this object are changed."""
        self.base.add_on_change(callback_id, on_change)
    
    def clear_on_change(self, callback_id):
        """Remove all callbacks registered with the given callback_id."""
        self.base.clear_on_change(callback_id)
    
    def add_on_specific_change(self, key, on_change):
        """Register a callback to be run whenever the value for the specific key in this object is changed."""
        pass # TODO: 
    
    def validate_all(self):
        """Check if all rules pass validation."""
        for rule in self.get_rules():
            for key in ValidatedSettings.get_keys_for_rule(rule):
                value = self.get(key)
                #if value is not None:
                ValidatedSettings.validate_rule(rule, key, value)
    
    def validate_key_value_pair(self, key, value):
        """Check if the specific key and value pass the validation rules."""
        for rule in self.get_rules():
            if key in ValidatedSettings.get_keys_for_rule(rule):
                ValidatedSettings.validate_rule(rule, key, value)
    
    @staticmethod
    def get_keys_for_rule(rule):
        if 'keys' in rule and 'key' in rule:
            raise ValueError('Illegal to use key and keys at the same time')
        
        keys = rule.get('keys', [])
        if not isinstance(keys, list):
            raise ValueError('keys must be a list')
        if 'key' in rule:
            keys.append(rule['key'])
        
        return keys
    
    def get_rules(self):
        #file_name = os.path.splitext(self.base_file_name)[0]
        #file_name += '_settings.json'
        file_name = self.base_file_name + '-rules'
        path = sublime.find_resources(file_name)[0]
        rules = sublime.decode_value(sublime.load_resource(path))
        return rules
    
    @staticmethod
    def validate_rule(rule, key, value):
        if 'type' in rule:
            type_class = None
            try:
                type_class = __builtins__[rule['type']]
            except KeyError:
                raise ValueError('rule for key "' + key + '" mentions type "' + rule['type'] + '" but this is not a built in Python type.')
                return
            if not isinstance(value, type_class):
                raise ValueError('"' + key + '" has type "' + type(value).__name__ + '" but should be "' + rule['type'] + '"')
        
        if 'allowed_values' in rule:
            if not value in rule['allowed_values']:
                raise ValueError('"' + key + '" has value: ' + repr(value) + ' but should be one of: ' + repr(rule['allowed_values']))


class SettingsViewListener(sublime_plugin.EventListener):
    key_selector = 'string.quoted.double.json'
    value_selector = 'meta.structure.dictionary.value.json'
    
    def get_related_settings(self, view):
        view_file_name = view.file_name()
        for base_file_name in ValidatedSettings.registered_settings:
            if view_file_name.endswith(base_file_name):
                return ValidatedSettings.registered_settings[base_file_name]
        return None
    
    def on_load_async(self, view):
        """When a ValidatedSettings file is loaded, register the necessary autocomplete triggers."""
        settings = self.get_related_settings(view)
        if settings:
            act = view.settings().get('auto_complete_triggers', list())
            act.append({ 'selector': 'source.json meta.structure.dictionary.json punctuation.definition.string.begin.json - meta.structure.dictionary.value.json ', 'characters': '"' })
            view.settings().set('auto_complete_triggers', act)
            
            if view.size() == 0:
                view.run_command('insert', { 'characters': '{\n"' })
                view.run_command('auto_complete')
    
    def on_query_completions(self, view, prefix, locations):
        settings = self.get_related_settings(view)
        if settings and view.match_selector(0, 'source.json'):
            if len(locations) == 1:
                pos = locations[0]
                key_selector = SettingsViewListener.key_selector
                value_selector = SettingsViewListener.value_selector
                if view.match_selector(pos, key_selector + ' - ' + value_selector): # keys
                    completions = list()
                    for rule in settings.get_rules():
                        keys = ValidatedSettings.get_keys_for_rule(rule)
                        append = ''
                        if 'type' in rule:
                            if rule['type'] == 'str':
                                append = '"$1"'
                            elif rule['type'] == 'list':
                                append = '[$1]'
                            else:
                                append = '$1'
                        
                        append = '": ' + append + ',\n'
                        completions += [(key + '\tKey', key + append) for key in keys]
                    return (completions, sublime.INHIBIT_WORD_COMPLETIONS)
                elif view.match_selector(pos, value_selector):
                    # get the relevant key
                    pos -= 1
                    while not view.match_selector(pos, key_selector + ' punctuation.definition.string.end.json'):
                        pos -= 1
                    end_pos = pos
                    while not view.match_selector(pos, key_selector + ' punctuation.definition.string.begin.json'):
                        pos -= 1
                    start_pos = pos + 1
                    key = view.substr(sublime.Region(start_pos, end_pos))
                    
                    completions = list()
                    for rule in settings.get_rules():
                        if key in ValidatedSettings.get_keys_for_rule(rule):
                            if 'allowed_values' in rule:
                                completions += [(value + '\t' + key, value) for value in rule['allowed_values']]
                            elif 'type' in rule:
                                if rule['type'] == 'bool':
                                    completions += [('true\tBoolean', 'true'), ('false\tBoolean', 'false')]
                    
                    return (completions, sublime.INHIBIT_WORD_COMPLETIONS)
        else:
            return None
    
    def on_post_text_command(self, view, command_name, args):
        settings = self.get_related_settings(view)
        if settings:
            if command_name in ('commit_completion', 'insert_best_completion'):
                if view.match_selector(view.sel()[0].begin(), SettingsViewListener.value_selector):
                    view.run_command('auto_complete')
