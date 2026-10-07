from voight.core.validator import GiftAnalyzer

def test_analyzer_basic(tmp_path):
    f1 = tmp_path / "q1.gift"
    f1.write_text("::Q1:: Text {=A}")
    f2 = tmp_path / "q2.gift"
    f2.write_text("::Q2:: Text {=B}")
    
    analyzer = GiftAnalyzer(recursive=False)
    analyzer.scan_directory(str(tmp_path))
    
    assert analyzer.stats.total_questions == 2
    assert analyzer.stats.total_files == 2

def test_analyzer_duplicates(tmp_path):
    f1 = tmp_path / "q1.gift"
    f1.write_text("::Q1:: Same text {=A}")
    f2 = tmp_path / "q2.gift"
    f2.write_text("::Q2:: Same text {=A}")
    
    analyzer = GiftAnalyzer(similarity_threshold=0.5, recursive=False)
    analyzer.scan_directory(str(tmp_path))
    analyzer.find_duplicates()
    
    assert len(analyzer.duplicates) == 1


def test_alias_gift_analyzer():
    from voight.core.validator import AnalizadorBanco

    assert GiftAnalyzer is AnalizadorBanco
