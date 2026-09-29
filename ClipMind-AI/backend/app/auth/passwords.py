"""Password hashing helpers."""

from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher


password_hasher = PasswordHash.recommended()
bcrypt_hasher = BcryptHasher()


def hash_password(password: str) -> str:
    """Return an Argon2id hash; the plain password is never persisted."""

    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify legacy bcrypt and current Argon2id hashes without rewriting them."""

    if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        return bcrypt_hasher.verify(password, password_hash)
    return password_hasher.verify(password, password_hash)
