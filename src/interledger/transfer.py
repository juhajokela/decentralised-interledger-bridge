from dataclasses import (
    asdict,
    dataclass,
)

@dataclass
class Transfer:
    id: str
    data: bytes
    initiator_id: str
    initiation_timestamp: int
    initiator_tx_key: str

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def short_id(self) -> str:
        return self.id[:5]
