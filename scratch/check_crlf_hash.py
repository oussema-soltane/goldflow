import hashlib
from pathlib import Path

content = Path("configs/candidate_specs/smc_confluence_v2.json").read_bytes()
print("Raw byte length:", len(content))
print("Raw SHA256:", hashlib.sha256(content).hexdigest())

# Normalize to LF
content_lf = content.replace(b"\r\n", b"\n")
print("LF SHA256:", hashlib.sha256(content_lf).hexdigest())

# Normalize to CRLF
content_crlf = content_lf.replace(b"\n", b"\r\n")
print("CRLF SHA256:", hashlib.sha256(content_crlf).hexdigest())

# Check expected
expected = "1eaa40373f9e89c3f65fb216badd6604fa7df428c973cf495902bf8a0bd7eb8c"
print("Expected:", expected)
if hashlib.sha256(content_lf).hexdigest() == expected:
    print("MATCHES WITH LF!")
elif hashlib.sha256(content_crlf).hexdigest() == expected:
    print("MATCHES WITH CRLF!")

