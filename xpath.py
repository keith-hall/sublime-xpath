import sublime
import sublime_plugin
import os
from itertools import takewhile

changeCounters = {}
XPaths = {}
supportHTML = True
settings = None

def settingsChanged():
    """Clear change counters and cached xpath regions for all views, and recalculate xpath regions for the current view."""
    global changeCounters
    global XPaths
    changeCounters.clear()
    XPaths.clear()
    updateStatusIfSGML(sublime.active_window().active_view())

def addPath(view, start, end, path):
    global XPaths
    XPaths[view.id()].append([sublime.Region(start, end), path[:]])

def clearPathsForView(view):
    """Clear all cached xpaths for the specified view."""
    global XPaths
    XPaths.pop(view.id(), None)

def buildPathsForView(view):
    """Clear and recreate a cache of all xpaths for the XML in the specified view."""
    clearPathsForView(view)
    global XPaths
    XPaths[view.id()] = []
    
    path = ['']
    levelCounters = [{}]
    firstIndexInXPath = 1
    
    tagRegions = view.find_by_selector('entity.name.tag.')
    position = 0
    
    global settings
    settings = sublime.load_settings('xpath.sublime-settings')
    settings.clear_on_change('reparse')
    settings.add_on_change('reparse', settingsChanged)
    wanted_attributes = settings.get('attributes_to_include', [])
    all_attributes = bool(settings.get('show_all_attributes', False))
    case_sensitive = bool(settings.get('case_sensitive', True))
    
    if not case_sensitive:
        wanted_attributes = [element.lower() for element in wanted_attributes]
    
    for region in tagRegions:
        prevChar = view.substr(sublime.Region(region.begin() - 1, region.begin()))
        tagName = view.substr(region)
        
        if prevChar == '<':
            addPath(view, position, region.begin(), path)
            
            # check last char before end of tag, to see if it is self closing or not...
            tagScope = view.find('>', region.end(), sublime.LITERAL).end()
            selfEndingTag = view.substr(tagScope - 2) == '/'
            
            position = tagScope
            
            attributes = []
            attr_pos = region.end() + 1
            attr_namespace = ''
            attr_name = ''
            while attr_pos < tagScope:
                scope_name = view.scope_name(attr_pos)
                scope_region = view.extract_scope(attr_pos)
                
                attr_pos = scope_region.end() + 1
                if 'entity.other.attribute-name' in scope_name:
                    scope_text = view.substr(scope_region)
                    if scope_text.endswith(':'):
                        attr_namespace = scope_text#[0:-1]
                        attr_pos -= 1
                    elif scope_text.startswith(':'):
                        attr_name = scope_text[1:]
                    else:
                        attr_name = scope_text
                elif 'string.quoted.' in scope_name:
                    scope_text = view.substr(scope_region)
                    if (all_attributes or
                        (    case_sensitive and (attr_namespace         + attr_name         in wanted_attributes or '*:' + attr_name         in wanted_attributes or attr_namespace         + '*' in wanted_attributes)) or
                        (not case_sensitive and (attr_namespace.lower() + attr_name.lower() in wanted_attributes or '*:' + attr_name.lower() in wanted_attributes or attr_namespace.lower() + '*' in wanted_attributes))
                    ):
                        attributes.append('@' + attr_namespace + attr_name + ' = ' + scope_text)
                    attr_namespace = ''
                    attr_name = ''
            
            if len(attributes) > 0:
                attributes = '[' + ' and '.join(attributes) + ']'
            else:
                attributes = ''
            
            level = len(levelCounters) - 1
            checkTag = tagName
            if not case_sensitive:
                checkTag = checkTag.lower()
            levelCounters[level][checkTag] = levelCounters[level].setdefault(checkTag, firstIndexInXPath - 1) + 1
            tagIndexAtCurrentLevel = levelCounters[level].get(checkTag)
            path.append(tagName + '[' + str(tagIndexAtCurrentLevel) + ']' + attributes)
            
            addPath(view, region.begin(), position, path)
            if selfEndingTag:
                path.pop()
            else:
                levelCounters.append({})
        elif prevChar == '/':
            addPath(view, position, region.begin(), path)
            addPath(view, region.begin(), region.end() + 1, path)
            path.pop()
            levelCounters.pop()
            position = region.end() + 1
        
    addPath(view, position, view.size(), path)

def getXPathIndexesAtPositions(view, positions):
    """Given a sorted array of regions, return the indexes of the xpath strings that relate to each region."""
    global XPaths
    count = len(positions)
    current = 0
    matches = []
    for index, path in enumerate(XPaths[view.id()]):
        if path[0].intersects(positions[current]) or path[0].begin() == positions[current].begin():
            matches.append(index)
            current += 1
            if current == count:
                break
    return matches

def getXPathAtPositions(view, positions):
    """Given a sorted array of regions, return the xpath nodes that relate to each region."""
    global XPaths
    matches = []
    for index in getXPathIndexesAtPositions(view, positions):
        matches.append(XPaths[view.id()][index][1])
    return matches

def getXPathStringAtPositions(view, positions, includeIndexes, includeAttributes):
    """Given a sorted array of regions, return the xpath strings that relate to each region."""
    global XPaths
    matches = []
    for match in getXPathAtPositions(view, positions):
        if includeIndexes and includeAttributes:
            matches.append('/'.join(match))
        else:
            hierarchy = []
            for part in match:
                begin = part.find('[')
                end = part.find(']', begin) + len(']')
                index = part[begin:end]
                attributes = part[end:]
                part = part[0:begin]
                
                if includeIndexes:
                    part += index
                if includeAttributes:
                    part += attributes
                
                hierarchy.append(part)
            matches.append('/'.join(hierarchy))
            
    return matches

def isSGML(view):
    """Return True if the view's syntax is XML or HTML."""
    global supportHTML
    return view.score_selector(0, 'text.xml') > 0 or (supportHTML and view.score_selector(0, 'text.html') > 0)

def updateStatusIfSGML(view):
    """Update the status bar with the relevant xpath at the cursor if the syntax is XML."""
    if isSGML(view) and len(view.sel()) > 0:
        updateStatus(view)
    else:
        view.erase_status('xpath')

def ensureXpathCacheIsCurrent(view):
    """If the XML has changed since the xpaths were cached, recreate the cache."""
    global changeCounters
    newCount = view.change_count()
    oldCount = changeCounters.get(view.id(), None)
    if oldCount is None or newCount > oldCount:
        changeCounters[view.id()] = newCount
        view.set_status('xpath', 'XPath being calculated...')
        buildPathsForView(view)

def updateStatus(view):
    """If the XML has changed since the xpaths were cached, recreate the cache. Updates the status bar with the xpath at the location of the first selection in the view."""
    ensureXpathCacheIsCurrent(view)
    
    includeIndexes = not getBoolValueFromArgsOrSettings('show_hierarchy_only', None, False)
    response = getXPathStringAtPositions(view, [view.sel()[0]], includeIndexes, includeIndexes or getBoolValueFromArgsOrSettings('show_attributes_in_hierarchy', None, False))
    if len(response) == 1 and len(response[0]) > 0:
        showPath = response[0]
        intro = 'XPath'
        if len(view.sel()) > 1:
            intro = intro + ' (at first selection)'
        view.set_status('xpath', intro + ': ' + showPath)
    else:
        view.erase_status('xpath')

def getBoolValueFromArgsOrSettings(key, args, default):
    if args is None or not key in args:
        global settings
        settings = sublime.load_settings('xpath.sublime-settings')
        return bool(settings.get(key, default))
    else:
        return args[key]

def copyXPathsToClipboard(view, includeIndexes, includeAttributes, unique):
    if isSGML(view):
        ensureXpathCacheIsCurrent(view)
        paths = getXPathStringAtPositions(view, view.sel(), includeIndexes, includeAttributes)
        if unique:
            unique = []
            for path in paths:
                if path not in unique:
                    unique.append(path)
            paths = unique
        sublime.set_clipboard(os.linesep.join(paths))
        sublime.status_message('xpath(s) copied to clipboard')
    else:
        global supportHTML
        message = 'xpath not copied to clipboard - ensure syntax is set to xml'
        if supportHTML:
            message += ' or html'
        sublime.status_message(message)

class XpathCommand(sublime_plugin.TextCommand):
    def run(self, edit, **args):
        """Copy XPath(s) at cursor(s) to clipboard."""
        view = self.view
        
        includeIndexes = not getBoolValueFromArgsOrSettings('show_hierarchy_only', args, False)
        unique = getBoolValueFromArgsOrSettings('copy_unique_path_only', args, True)
        includeAttributes = includeIndexes or getBoolValueFromArgsOrSettings('show_attributes_in_hierarchy', args, False)
        
        copyXPathsToClipboard(view, includeIndexes, includeIndexes or includeAttributes, unique)
    def is_enabled(self):
        return isSGML(self.view)
    def is_visible(self, **args):
        return isSGML(self.view)

class GotoRelativeCommand(sublime_plugin.TextCommand):
    def run(self, edit, **args): #sublime.active_window().active_view().run_command('goto_relative', {'event': {'y': 351.5, 'x': 364.5}, 'direction': 'prev'})
        """Move cursor(s) to specified relative tag(s)."""
        view = self.view
        
        foundPaths = []
        allFound = True
        for selection in view.sel():
            foundPath = self.find_node(selection, args['direction'])
            if foundPath is not None:
                foundPaths.append(foundPath)
            else:
                allFound = False
                break
        
        if not allFound:
            message = args['direction'] + ' node not found'
            if len(view.sel()) > 1:
                message += ' for at least one selection'
            sublime.status_message(message)
        else:
            view.sel().clear()
            for foundPath in foundPaths:
                view.sel().add(foundPath)
            view.show(foundPaths[0]) # scroll to first selection if not already visible
    
    def find_node(self, relative_to, direction):
        """Find specified relative tag."""
        view = self.view
        
        global XPaths
        
        currentPos = getXPathIndexesAtPositions(view, [relative_to])[0]
        currentPath = XPaths[view.id()][currentPos][1]
        parentPath = '/'.join(currentPath[0:-1])
        currentPath = '/'.join(currentPath)
        
        if direction in ('next', 'close'):
            search = XPaths[view.id()][currentPos:] # search from current position down to the end of the document
        else: # prev, parent or open
            search = XPaths[view.id()][0:currentPos + 1] # search from current position up to the top of the document
            search = search[::-1]
        
        foundPaths = takewhile(lambda p: '/'.join(p[1]).startswith(parentPath), search)
        if direction == 'next':
            foundPath = next((p for p in foundPaths if '/'.join(p[1]) != parentPath and not '/'.join(p[1]).startswith(currentPath)), None) # not the parent node and not a descendant of the current node
        elif direction == 'prev':
            foundPath = None
            wantedPath = None
            for path in foundPaths:
                p = '/'.join(path[1])
                if not p.startswith(parentPath + '/'): # if it isn't a descendant of the parent, ignore it
                    pass
                elif wantedPath is not None:
                    if p == wantedPath: # if it is the same sibling we have already found
                        foundPath = path
                    elif not p.startswith(wantedPath):
                        break
                elif not p.startswith(currentPath):
                    foundPath = path
                    wantedPath = '/'.join(foundPath[1])
        elif direction in ('open', 'close', 'parent'):
            if direction == 'parent':
                wantedPath = parentPath
            else:
                wantedPath = currentPath
            foundPaths = list(p for p in foundPaths if '/'.join(p[1]) == wantedPath)
            if len(foundPaths) > 0:
                foundPath = foundPaths[-1] # the last node (open and parent are in reverse order, remember...)
            else:
                foundPath = None
        
        if foundPath is None:
            return None
        else:
            return sublime.Region(foundPath[0].begin(), foundPath[0].end() - 1)
    
    #def want_event(self):
    #    return True
    def is_enabled(self):
        return isSGML(self.view)
    def is_visible(self):
        return isSGML(self.view)
    def description(self, args):
        if args['direction'] in ('open', 'close'):
            descr = 'tag'
        elif args['direction'] in ('prev', 'next'):
            descr = 'sibling'
        elif args['direction'] in ('parent'):
            descr = 'element'
        else:
            return None
        
        return 'Goto ' + args['direction'] + ' ' + descr


class XpathListener(sublime_plugin.EventListener):
    def on_selection_modified_async(self, view):
        updateStatusIfSGML(view)
    def on_activated_async(self, view):
        updateStatusIfSGML(view)
    def on_pre_close(self, view):
        clearPathsForView(view)
