class FileverError(Exception):
    pass


class NoVersionFound(FileverError):
    pass


class AmbiguousVersion(FileverError):
    pass


class NoDriverToken(FileverError):
    pass


class UnresolvedPlaceholder(FileverError):
    pass
