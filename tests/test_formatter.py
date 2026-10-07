from voight.core.formatter import format_gift_content, fix_code_indentation, convert_markdown_code_blocks

def test_format_gift_content():
    content = "::Title::Question{=Ans~Wrong}"
    formatted = format_gift_content(content)
    
    # Check if it added newlines and spaces
    assert "::Title::" in formatted
    assert "{" in formatted
    assert "    =Ans" in formatted
    assert "}" in formatted

def test_fix_code_indentation():
    content = "```python\n    print('hello')\n```"
    fixed, count = fix_code_indentation(content)
    
    assert count == 1
    assert "····print('hello')" in fixed

def test_convert_markdown_code_blocks():
    content = "Check this: `x == y`"
    # To fullwidth
    converted, count = convert_markdown_code_blocks(content, to_normal=False)
    assert count == 1
    assert "x ⩵ y" in converted
    
    # Back to normal
    normal, count = convert_markdown_code_blocks(converted, to_normal=True)
    assert count == 1
    assert "x == y" in normal
