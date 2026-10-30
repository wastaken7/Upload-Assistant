from src.args import Args
from src.meta import Meta


def test_hardcoded_subtitle_language_cli_argument(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse(
        [str(tmp_path), "--hardcoded-subs", "--hardcoded-subs-language", "Portuguese"], Meta()
    )

    assert meta.hardcoded_subs is True  # noqa: S101
    assert meta.hardcoded_subs_language == "Portuguese"  # noqa: S101


def test_hardcoded_subtitle_language_implies_hardcoded_subs(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse([str(tmp_path), "--hardcoded-subs-language", "English"], Meta())

    assert meta.hardcoded_subs is True  # noqa: S101
    assert meta.hardcoded_subs_language == "English"  # noqa: S101
