from voight.core.splitter import split_file

def test_split_file(tmp_path):
    content = "::Q1::\nText 1{=A}\n\n::Q2::\nText 2{=B}"
    f = tmp_path / "test.gift"
    f.write_text(content)
    
    count = split_file(f)
    assert count == 2
    
    # Check generated files
    assert (tmp_path / "q1.gift").exists()
    assert (tmp_path / "q2.gift").exists()
    assert (tmp_path / "q1.gift").read_text().strip() == "::Q1::\nText 1{=A}"
