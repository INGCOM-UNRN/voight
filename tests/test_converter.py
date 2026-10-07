from voight.core.converter import convert_html_tags_to_markdown

def test_convert_html_tags_to_markdown():
    html = "<code>code</code> <p>para</p> <strong>bold</strong>"
    md = convert_html_tags_to_markdown(html)
    
    assert "`code`" in md
    assert "**bold**" in md
    assert "para" in md

def test_convert_fullwidth_html_tags():
    html = "＜code＞code＜/code＞ ＜p＞para＜/p＞"
    md = convert_html_tags_to_markdown(html)
    
    assert "`code`" in md
    assert "para" in md
