import enum
from dataclasses import dataclass


class UserRole(str, enum.Enum):
    UNSPECIFIED = "unspecified"
    NORMAL_USER = "normal_user"
    PRIVILEGED_USER = "privileged_user"
    ADMIN = "admin"


@dataclass
class User:
    user_id: str
    role: UserRole


__all__ = ["User", "UserRole"]
