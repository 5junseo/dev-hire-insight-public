import hashlib

def make_hash(text: str) -> str:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()