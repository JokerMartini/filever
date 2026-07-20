"""Process-level configuration flags for filever.

Set once at pipeline startup:

    from filever import config
    config.strict_pad = False

Flags:
    strict_pad -- When True (default), disk scans only include entries whose
                  digit width matches what the seed's pad would format for that
                  value. When False, entries of any pad width are included and
                  each returned VersionedFile carries the pad of its actual
                  on-disk entry.
"""

strict_pad: bool = True
