class ValidationError(ValueError):
    """A blocking gate failure with safe, relative context."""


class SourceValidationError(ValidationError):
    pass


class GeometryValidationError(ValidationError):
    pass


class ArtifactValidationError(ValidationError):
    pass
