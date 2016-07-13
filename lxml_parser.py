from lxml import etree
from lxml.html import fromstring as fromhtmlstring
import collections
import re

def clean_html(html_soup):
    """Convert the given html tag soup string into a valid xml string."""
    root = fromhtmlstring(html_soup)
    return etree.tostring(root, encoding='unicode')


class CommonEqualityMixin(object): # inspired by http://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
    def __eq__(self, other):
        if type(other) is type(self):
            return self.__dict__ == other.__dict__
        return NotImplemented
    
    def __ne__(self, other):
        return not self.__eq__(other)


class TagPos(CommonEqualityMixin):
    def __init__(self, start, end):
        self.start_pos = start
        self.end_pos = end
    
    def __repr__(self):
        return self.__class__.__name__ + ': ' + str(self.start_pos) + ', ' + str(self.end_pos)
    

class LocationAwareElement(etree.ElementBase):
    open_tag_pos = None
    close_tag_pos = None
    
    def is_self_closing(self):
        """If the start and end tag positions are the same, then it is self closing."""
        return self.open_tag_pos == self.close_tag_pos


class LocationAwareComment(etree.CommentBase):
    tag_pos = None


# http://stackoverflow.com/questions/36246014/lxml-use-default-class-element-lookup-and-treebuilder-parser-target-at-the-sam
class LocationAwareXMLParser:
    SPLIT_XML_TOKENS = [('<![CDATA[', ']]>'), ('<!--', '-->'), ('<', '>')]
    LARGEST_BEGIN_TOKEN = max([begin for begin, end in SPLIT_XML_TOKENS], key=len)
    LARGEST_END_TOKEN = max([end for begin, end in SPLIT_XML_TOKENS], key=len)
    LARGEST_TOKEN = len(max(LARGEST_BEGIN_TOKEN, LARGEST_END_TOKEN))
    
    def __init__(self, position_offset = 0, line_number_offset = 0, **parser_options):
        def getLocation():
            if len(self._positions) < 3: # prevent IndexError while the XML root element is still being written i.e. the entire contents of the document is just: <test
                return None
            return TagPos(self._positions[-3], self._positions[-1])
        
        class Target:
            start = lambda t, tag, attrib=None, nsmap=None: self.element_start(tag, attrib, nsmap, getLocation())
            end = lambda t, tag: self.element_end(tag, getLocation())
            data = lambda t, data: self.text_data(data, None)
            comment = lambda t, comment: self.comment(comment, getLocation())
            pi = lambda t, target, data: self.pi(target, data, getLocation())
            doctype = lambda t, name, public_identifier, system_identifier: self.doctype(name, public_identifier, system_identifier, getLocation())
            close = lambda t: self.document_end()
        
        self._parser = etree.XMLParser(target=Target(), **parser_options)
        self._initial_position_offset = position_offset
        self._initial_line_number_offset = line_number_offset
        self._reset()
    
    def _reset(self):
        self._position_offset = self._initial_position_offset
        self._positions = []
        self._line_number = 1 + self._initial_line_number_offset
        self._column_number = 1
        self._expect_end = None
        self._remainder = ''
        self._is_final_chunk = False
    
    def feed(self, chunk):
        # NOTE: it doesn't support DOCTYPE nesting, but such things are not represented in the tree anyway, and after the doctypes, it should get the locations correct again
        chunk = self._remainder + chunk
        
        # if the position is not far enough from the end of the string to rule out what it isn't
        # - i.e. if our chunk ends with "hello world<", we need more data before we know if it is a <![CDATA[ or a <!-- or just a <
        process_until = len(chunk) - (self.LARGEST_TOKEN if not self._is_final_chunk else 0)
        if process_until < 0:
            process_until = 0
        chunk_offset = 0
        
        while chunk_offset < process_until:
            # if we previously found a beginning token but have not yet found the corresponding end token
            if self._expect_end is not None:
                pos = chunk.find(self._expect_end, chunk_offset, process_until)
                if pos == -1:
                    break
                else:
                    # feed everything before the matching end sequence
                    self._feed(chunk[chunk_offset:pos], (self._position_offset, self._position_offset + pos))
                    
                    # feed the end sequence itself
                    self._feed(self._expect_end, (self._position_offset + pos, self._position_offset + pos + len(self._expect_end)))
                    
                    chunk_offset = pos + len(self._expect_end)
                    self._expect_end = None
            
            # if we are not looking for an end token
            if self._expect_end is None:
                # find the next sigificant XML control char, so we can manually know the location
                pos = chunk.find('<', chunk_offset, process_until)
                if pos == -1:
                    break
                else:
                    for begin_token, end_token in self.SPLIT_XML_TOKENS:
                        if chunk.find(begin_token, pos, pos + len(begin_token)) == pos:
                            self._expect_end = end_token
                            break
                    
                    # feed everything before the match
                    pos1 = self._position_offset + pos
                    self._feed(chunk[chunk_offset:pos], (self._position_offset + chunk_offset, pos1))
                    
                    # feed the "begin" sequence itself
                    pos2 = pos1 + len(begin_token)
                    self._feed(begin_token, (pos1, pos2))
                    
                    chunk_offset = pos + len(begin_token)
        
        if process_until < chunk_offset:
            process_until = chunk_offset
        
        # feed the rest of the chunk
        self._position_offset += process_until
        self._feed(chunk[chunk_offset:process_until], None)
        self._remainder = chunk[process_until:]
    
    def _feed(self, text, position):
        if position is not None:
            self._positions.append(position)
        if len(text) > 0:
            self._parser.feed(bytes(text, 'UTF-8')) # feed as bytes, otherwise doesn't work on OSX, and encoding declarations in the prolog can cause exceptions - http://lxml.de/parsing.html#python-unicode-strings
            line_count = text.count('\n')
            if line_count > 0:
                self._line_number += line_count
                self._column_number = len(text) - text.rfind('\n')
            else:
                self._column_number += len(text)
    
    def close(self):
        self._is_final_chunk = True
        self.feed('')
        result = self._parser.close()
        self._reset()
        return result
    
    def element_start(self, tag, attrib=None, nsmap=None, location=None):
        pass
    
    def element_end(self, tag, location=None):
        pass
    
    def text_data(self, data, location=None):
        pass
    
    def comment(self, comment, location=None):
        pass
    
    def pi(self, target, data, location=None):
        pass
    
    def doctype(self, name, public_identifier, system_identifier, location=None):
        pass
    
    def document_end(self):
        pass


class LocationAwareTreeBuilder(LocationAwareXMLParser):
    def _reset(self):
        super()._reset()
        self._all_elements = [] # necessary to keep the "proxy" alive, so it will keep our custom class attributes - otherwise, when the class instance is recreated, it no longer has the position information - see http://lxml.de/element_classes.html#element-initialization
        self._element_stack = []
        self._text = []
        self._most_recent = None
        self._in_tail = None
        self._all_namespaces = collections.OrderedDict()
        self._root = None
    
    def _flush(self):
        if self._text:
            value = ''.join(self._text)
            if self._most_recent is None and value.strip() == '':
                pass
            elif self._in_tail:
                self._most_recent.tail = value
            else:
                self._most_recent.text = value
            self._text = []
    
    def element_start(self, tag, attrib=None, nsmap=None, location=None):
        for prefix in nsmap:
            namespaces = self._all_namespaces.setdefault(prefix, [])
            if nsmap[prefix] not in namespaces:
                namespaces.append(nsmap[prefix])
        
        self._flush()
        self._appendNode(self.create_element(tag, attrib, nsmap))
        self._element_stack.append(self._most_recent)
        self._most_recent.open_tag_pos = location
        self._in_tail = False
    
    def create_element(self, tag, attrib=None, nsmap=None):
        LocationAwareElement.TAG = tag
        new_element = None
        try:
            new_element = LocationAwareElement(attrib=attrib, nsmap=nsmap)
        except ValueError as e:
            raise etree.XMLSyntaxError(e.args[0] + ' at line ' + str(self._line_number - 1) + ', column ' + str(self._column_number), None, self._line_number, self._column_number)
        return new_element
    
    def element_end(self, tag, location=None):
        self._flush()
        self._most_recent = self._element_stack.pop()
        self._most_recent.close_tag_pos = location
        self._in_tail = True
    
    def text_data(self, data, location=None):
        self._text.append(data)
    
    def comment(self, text, location=None):
        if self._most_recent is not None:
            self._flush()
            self._appendNode(self.create_comment(text))
            self._most_recent.tag_pos = location
            self._in_tail = True
    
    def create_comment(self, text):
        return LocationAwareComment(text)
    
    def _appendNode(self, node):
        if self._element_stack: # if we have anything on the stack
            self._element_stack[-1].append(node) # append the node as a child to the last/top element on the stack
        elif self._root is None and isinstance(node, etree.ElementBase):
            self._root = node
        self._all_elements.append(node)
        self._most_recent = node
    
    def document_end(self):
        """Return the root node and a list of all elements (and comments) found in the document, to keep their proxy alive."""
        return (self._root, self._all_namespaces, self._all_elements)


def lxml_etree_parse_xml_string_with_location(xml_chunks, position_offset = 0, line_number_offset = 0, should_stop = None):
    target = LocationAwareTreeBuilder(position_offset=position_offset, line_number_offset=line_number_offset, collect_ids=False, huge_tree=True, remove_blank_text=False)
    
    if should_stop is None or not callable(should_stop):
        should_stop = lambda: False
    
    for chunk in xml_chunks: # for each xml chunk fed to us
        if should_stop():
            break
        target.feed(chunk)
    
    root, all_namespaces, all_elements = target.close()
    tree = etree.ElementTree(root)
    
    root.all_namespaces = all_namespaces
    
    return (tree, all_elements)

# TODO: consider moving to LocationAwareElement class
def getNodeTagRange(node, position_type):
    """Given a node and position type (open or close), return the node's position."""
    pos = None
    if isinstance(node, LocationAwareComment):
        pos = node.tag_pos
    else:
        pos = getattr(node, position_type + '_tag_pos')
    #assert pos is not None, repr(node) + ' ' + position_type
    return (pos.start_pos[0], pos.end_pos[1])

def getRelativeNode(relative_to, direction):
    """Given a node and a direction, return the node that is relative to it in the specified direction, or None if there isn't one."""
    def return_specific(node):
        yield node
    generator = None
    if direction == 'next':
        generator = relative_to.itersiblings()
    elif direction in ('prev', 'previous'):
        generator = relative_to.itersiblings(preceding = True)
    elif direction == 'self':
        generator = return_specific(relative_to) # return self
    elif direction == 'parent':
        generator = return_specific(relative_to.getparent())
    
    if generator is None:
        raise ValueError('Unknown direction "' + direction + '"')
    else:
        return next(generator, None)

# TODO: move to Element subclass?
def getTagName(node):
    """Return the namespace URI, the local name of the element, and the full name of the element including the prefix."""
    q = etree.QName(node)
    full_name = q.localname
    if node.prefix is not None:
        full_name = node.prefix + ':' + full_name
    return (q.namespace, q.localname, full_name)

def collapseWhitespace(text, maxlen):
    """Replace tab characters and new line characters with spaces, trim the text and convert multiple spaces into a single space, and optionally truncate the result at maxlen characters."""
    text = (text or '').strip()[0:maxlen + 1].replace('\n', ' ').replace('\t', ' ')
    while '  ' in text:
        text = text.replace('  ', ' ')
    if maxlen < 0: # a negative maxlen means infinite/no limit
        return text
    else:
        append = ''
        if len(text) > maxlen:
            append = '...'
        return text[0:maxlen - len(append)] + append

def unique_namespace_prefixes(namespaces, replaceNoneWith = 'default', start = 1):
    """Given an ordered dictionary of unique namespace prefixes and their URIs in document order, create a dictionary with unique namespace prefixes and their mappings."""
    unique = collections.OrderedDict()
    for key in namespaces.keys():
        if len(namespaces[key]) == 1:
            try_key = key or replaceNoneWith
            unique[try_key] = (namespaces[key][0], key)
        else: # find next available number. we can't just append the number, because it is possible that the new numbered prefix already exists
            index = start - 1
            for item in namespaces[key]: # for each item that has the same prefix but a different namespace
                while True:
                    index += 1 # try with the next index
                    try_key = (key or replaceNoneWith) + str(index)
                    if try_key not in unique.keys() and try_key not in namespaces.keys():
                        break # the key we are trying is new
                unique[try_key] = (item, key)
    
    return unique

def get_results_for_xpath_query(query, tree, context = None, namespaces = None, **variables):
    """Given a query string and a document trees and optionally some context elements, compile the xpath query and execute it."""
    nsmap = {}
    if namespaces is not None:
        for prefix in namespaces.keys():
            nsmap[prefix] = namespaces[prefix][0]
    
    xpath = etree.XPath(query, namespaces = nsmap)
    
    results = execute_xpath_query(tree, xpath, context, **variables)
    return results

def execute_xpath_query(tree, xpath, context_node = None, **variables):
    """Execute the precompiled xpath query on the tree and return the results as a list."""
    if context_node is None: # explicitly check for None rather than using "or", because it is treated as a list
        context_node = tree
    if isinstance(context_node, etree.CommentBase):
        context_node = context_node.getparent()
    result = xpath(context_node, **variables)
    if isinstance(result, list):
        return result
    else:
        return [result]
