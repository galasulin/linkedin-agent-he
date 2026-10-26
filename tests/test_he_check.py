"""Smoke tests for scripts/he_check.py (run: python -m pytest tests)."""
import importlib.util, os

HERE = os.path.dirname(__file__)
spec = importlib.util.spec_from_file_location("he_check", os.path.join(HERE, "..", "scripts", "he_check.py"))
hc = importlib.util.module_from_spec(spec); spec.loader.exec_module(hc)

def read(name):
    return open(os.path.join(HERE, "..", "examples", name), encoding="utf-8").read()

def test_fix_removes_em_dash_and_invisible_chars():
    clean, changes = hc.fix("שלום​ — עולם")
    assert "—" not in clean and "​" not in clean and changes

def test_stock_phrases_are_flagged():
    phrases = [p for p, _, _ in hc.slop_hits(read("sample-draft.txt"))]
    assert "בעולם של היום" in phrases and "חשוב לציין" in phrases and "לסיכום" in phrases

def test_rewrite_scores_higher_than_draft():
    _, draft, _, _, _ = hc.score(read("sample-draft.txt"))
    _, final, _, _, _ = hc.score(read("sample-final.txt"))
    assert final > draft

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
