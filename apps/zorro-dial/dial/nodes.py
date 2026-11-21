"""Tiles in a tree: telling them apart, and the key their unfolded children are kept under."""


def same(a, b):
    """the same button? Tiles are made new on every redraw, so compare what they are"""
    if a is b:
        return True
    if not a or not b:
        return False
    return what(a) == what(b)


def what(x):
    return (x.get('id'), x.get('name'), x.get('icon'), x.get('more'), x.get('gear'))


def node_key(node):
    return node.get('id') or node.get('name')


def cache_key(part_key, node):
    """per part: Files and Notes both have a 'recent', and must not show each other's"""
    return (part_key, node_key(node))
