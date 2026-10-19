from riskgate.diffparse import FileChange
from riskgate.testgaps import find_gaps, untested

SRC = '''def covered(x):
    return x + 1


def uncovered(x):
    y = x * 2
    return y


class Calc:
    def method(self, a):
        return a - 1

    def _private(self):
        return 0
'''


def make_repo(tmp_path, test_body="from pkg.mod import covered\n\ndef test_c():\n    assert covered(1) == 2\n"):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(SRC)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_mod.py").write_text(test_body)
    return tmp_path


def test_maps_changed_lines_to_functions_and_flags_untested(tmp_path):
    root = make_repo(tmp_path)
    change = FileChange("pkg/mod.py", added=["a", "b", "c", "d"], added_line_numbers=[2, 6, 12, 15])
    gaps = find_gaps([change], root=root)
    names = {g.qualname: g.referenced_by_tests for g in gaps}
    assert names == {"covered": True, "uncovered": False, "Calc.method": False, "Calc._private": False}
    todo = {g.qualname for g in untested(gaps)}
    assert todo == {"uncovered", "Calc.method"}  # private helpers are not demanded


def test_ignores_test_files_deleted_and_missing(tmp_path):
    root = make_repo(tmp_path)
    changes = [
        FileChange("tests/test_mod.py", added=["x"], added_line_numbers=[1]),
        FileChange("pkg/gone.py", status="deleted"),
        FileChange("pkg/not_there.py", added=["x"], added_line_numbers=[1]),
        FileChange("README.md", added=["x"], added_line_numbers=[1]),
    ]
    assert find_gaps(changes, root=root) == []


def test_syntax_error_source_is_skipped(tmp_path):
    root = make_repo(tmp_path)
    (root / "pkg" / "bad.py").write_text("def broken(:\n")
    assert find_gaps([FileChange("pkg/bad.py", added=["x"], added_line_numbers=[1])], root=root) == []


def test_mention_in_string_or_comment_is_not_coverage(tmp_path):
    body = '# uncovered is tested elsewhere\n"""uncovered"""\nfrom pkg.mod import covered\n\ndef test_c():\n    assert covered(1) == 2\n'
    root = make_repo(tmp_path, test_body=body)
    change = FileChange("pkg/mod.py", added=["x"], added_line_numbers=[6])
    assert [g.qualname for g in untested(find_gaps([change], root=root))] == ["uncovered"]


def test_attribute_call_counts_as_reference(tmp_path):
    body = "import pkg.mod as m\n\ndef test_u():\n    assert m.uncovered(2) == 4\n"
    root = make_repo(tmp_path, test_body=body)
    change = FileChange("pkg/mod.py", added=["x"], added_line_numbers=[6])
    assert untested(find_gaps([change], root=root)) == []
