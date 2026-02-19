from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseModule(ABC):
    key: str = "base"

    @abstractmethod
    def preprocess(self, text: str, req: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def build_system(self, req: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        raise NotImplementedError

    @abstractmethod
    def build_user(self, req: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        raise NotImplementedError

    @abstractmethod
    def postprocess(self, raw: str, req: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
