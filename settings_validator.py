import sublime
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
            path = sublime.find_resources(self.base_file_name)[0]
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
        self.base.set(name, value)
    
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
    
    def validate_all(self):
        """Check if all rules pass validation."""
        for rule in self.get_rules():
            for key in ValidatedSettings.get_keys_for_rule(rule):
                value = self.get(key)
                if value is not None:
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
            type_class = __builtins__[rule['type']]
            if not isinstance(value, type_class):
                raise ValueError('"' + key + '" has type "' + type(value).__name__ + '" but should be "' + rule['type'] + '"')
        
        if 'allowed_values' in rule:
            if not value in rule['allowed_values']:
                raise ValueError('"' + key + '" has value: ' + repr(value) + ' but should be one of: ' + repr(rule['allowed_values']))
