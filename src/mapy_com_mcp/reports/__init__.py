"""What the map tools report: route numbers, map and profile images.

Shared by the tools that show places or routes to the user and the ones that
let the agent look for itself, so both always say and draw the same thing.
HTTP goes through `MapyClient`; errors propagate, and each tool decides
whether a failure is fatal or a note.
"""
