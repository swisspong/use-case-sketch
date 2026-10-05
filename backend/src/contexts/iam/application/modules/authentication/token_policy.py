"""Application lifetime selection shared by login and admin_login only.

Other issuance channels have no confirmed lifetime rule yet. Production issuers
translate this duration into expiry and enforce it; they do not choose defaults.
"""

from datetime import timedelta
from typing import Final


LOGIN_ACCESS_TOKEN_TTL: Final[timedelta] = timedelta(minutes=15)
