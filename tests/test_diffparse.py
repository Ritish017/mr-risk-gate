from riskgate.diffparse import parse_unified_diff

GIT_DIFF = """diff --git a/tinyledger/billing.py b/tinyledger/billing.py
index 111..222 100644
--- a/tinyledger/billing.py
+++ b/tinyledger/billing.py
@@ -10,4 +10,5 @@ def money(value):
 context line
-old line
+new line one
+new line two
 tail
diff --git a/docs/new.md b/docs/new.md
new file mode 100644
--- /dev/null
+++ b/docs/new.md
@@ -0,0 +1,2 @@
+# Title
+--- not a header, just content
diff --git a/tests/test_old.py b/tests/test_old.py
deleted file mode 100644
--- a/tests/test_old.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def test_x():
-    assert True
"""


def test_parses_files_status_and_counts():
    files = parse_unified_diff(GIT_DIFF)
    assert [f.path for f in files] == ["tinyledger/billing.py", "docs/new.md", "tests/test_old.py"]
    billing, doc, old = files
    assert billing.status == "modified"
    assert billing.added == ["new line one", "new line two"]
    assert billing.removed == ["old line"]
    assert billing.added_line_numbers == [11, 12]
    assert doc.status == "added"
    assert doc.added[1] == "--- not a header, just content"
    assert old.status == "deleted"
    assert len(old.removed) == 2


def test_plain_diff_u_multiple_files():
    text = """--- a.py\t2026-01-01
+++ a.py\t2026-01-02
@@ -1 +1 @@
-x = 1
+x = 2
--- b.py\t2026-01-01
+++ b.py\t2026-01-02
@@ -1 +1,2 @@
 y = 1
+z = 3
"""
    files = parse_unified_diff(text)
    assert [f.path for f in files] == ["a.py", "b.py"]
    assert files[1].added_line_numbers == [2]


def test_rename_and_binary():
    text = """diff --git a/old.py b/new.py
similarity index 100%
rename from old.py
rename to new.py
diff --git a/logo.png b/logo.png
Binary files a/logo.png and b/logo.png differ
"""
    files = parse_unified_diff(text)
    assert files[0].status == "renamed" and files[0].path == "new.py" and files[0].old_path == "old.py"
    assert files[1].binary


def test_empty_diff():
    assert parse_unified_diff("") == []
