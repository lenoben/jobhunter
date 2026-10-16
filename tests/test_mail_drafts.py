import pytest

from core.mail_config import MailConfig
from core.mail_drafts import build_message, find_drafts_folder, parse_list_line


def folders(*lines):
    return [parse_list_line(line) for line in lines]


def test_prefers_special_use_flag():
    fs = folders(b'(\\HasNoChildren) "/" "Drafts"', b'(\\HasNoChildren \\Drafts) "/" "Entw&APw-rfe"')
    assert find_drafts_folder(fs) == ("Entw&APw-rfe", "\\Drafts flag")


def test_falls_back_to_yahoo_draft_name():
    fs = folders(b'(\\HasNoChildren) "/" "Inbox"', b'(\\HasNoChildren) "/" "Draft"',
                 b'(\\HasNoChildren) "/" "Sent"')
    assert find_drafts_folder(fs) == ("Draft", "name fallback")


def test_falls_back_to_drafts_name():
    fs = folders(b'(\\HasNoChildren) "/" "Inbox"', b'(\\HasNoChildren) "/" "Drafts"')
    assert find_drafts_folder(fs) == ("Drafts", "name fallback")


def test_no_drafts_folder_raises():
    with pytest.raises(RuntimeError):
        find_drafts_folder(folders(b'(\\HasNoChildren) "/" "Inbox"'))


def test_build_message_without_attachment():
    msg = build_message("me@myyahoo.com", "me@myyahoo.com", "JobHunter test", "Grüße")
    assert msg["Subject"] == "JobHunter test"
    assert list(msg.iter_attachments()) == []


def test_build_message_attaches_pdfs(tmp_path):
    cv, letter = tmp_path / "cv.pdf", tmp_path / "anschreiben.pdf"
    cv.write_bytes(b"%PDF-1.7 cv")
    letter.write_bytes(b"%PDF-1.7 letter")
    msg = build_message("me@myyahoo.com", "jobs@acme.example", "Bewerbung", "Text", [cv, letter])
    atts = list(msg.iter_attachments())
    assert [a.get_filename() for a in atts] == ["cv.pdf", "anschreiben.pdf"]
    assert all(a.get_content_type() == "application/pdf" for a in atts)
    assert atts[0].get_content() == b"%PDF-1.7 cv"


def test_config_repr_hides_password():
    assert "secret" not in repr(MailConfig("me@myyahoo.com", "secret"))
