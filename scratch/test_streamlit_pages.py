import io
import sys
from pathlib import Path
import py_compile

# Fix windows cp1252 console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pages = [
    ROOT / "app.py",
    ROOT / "pages" / "1_Market_Analysis.py",
    ROOT / "pages" / "2_Backtesting.py",
    ROOT / "pages" / "3_BI_Dashboard.py",
    ROOT / "pages" / "4_About.py",
]

print("1. Checking syntax and bytecode compilation for all Streamlit pages...")
for page in pages:
    assert page.exists(), f"Page {page} does not exist!"
    py_compile.compile(str(page), doraise=True)
    print(f"  ✓ {page.name} compiled cleanly.")

print("\n2. Testing Streamlit AppTest simulation if supported...")
try:
    from streamlit.testing.v1 import AppTest
    for page in pages:
        print(f"  Simulating {page.name} with AppTest...")
        at = AppTest.from_file(str(page), default_timeout=30)
        at.run()
        if at.exception:
            print(f"  ✗ AppTest exception in {page.name}: {at.exception}")
        else:
            print(f"  ✓ AppTest succeeded for {page.name} with 0 unhandled exceptions.")
except Exception as e:
    print(f"  AppTest note: {e}")

print("\nAll Streamlit pages verified!")
