# -*- coding: utf-8 -*-


def classFactory(iface):
    """Load the Attribute Consistency Checker plugin."""
    from .attribute_consistency_checker import AttributeConsistencyChecker
    return AttributeConsistencyChecker(iface)
