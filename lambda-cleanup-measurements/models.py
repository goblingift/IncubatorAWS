from dataclasses import dataclass, field

@dataclass
class ProcessingResult:
    is_valid: bool
    clean_item: dict = field(default_factory=dict)
    rejection_reasons: list = field(default_factory=list)
