import sublime
from uuid import uuid4 as guid

def get_scopes(view, start_at_position, stop_at_position):
    """Return the unique scopes in the view between start_at_position and stop_at_position, in the order in which they occur."""
    current_scope = None
    for pos in range(start_at_position, stop_at_position):
        scope = view.scope_name(pos)
        if current_scope is None:
            current_scope = (scope, pos, pos)
        elif current_scope[0] == scope: # if the current scope is exactly the same, extend it
            current_scope = (current_scope[0], current_scope[1], pos)
        else: # the previous scope is complete, register new one
            yield current_scope
            current_scope = (scope, pos, pos)
    if current_scope is not None:
        yield current_scope

def temporary_status_message(view, message, duration=5000):
    if hasattr(view.window(), 'status_message'): # this method was added in dev build 3110
        view.window().status_message(message)
    else:
        key = 'z_' + str(guid()) # ensure it appears after all other items in the status bar, as they are sorted by key
        view.set_status(key, message)
        sublime.set_timeout_async(lambda: view.erase_status(key), duration)
