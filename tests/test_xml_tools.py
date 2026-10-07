import xml.etree.ElementTree as ET
from voight.core.xml_tools import ensure_cdata_in_text_blocks, remove_tags_from_xml

def test_ensure_cdata():
    xml_content = "<question><text>Content</text></question>"
    new_content, count = ensure_cdata_in_text_blocks(xml_content)
    
    assert count == 1
    assert "<![CDATA[Content]]>" in new_content

def test_remove_tags():
    xml_content = """<quiz>
  <question>
    <tags><tag><text>t1</text></tag></tags>
    <name><text>Q1</text></name>
  </question>
</quiz>"""
    root = ET.fromstring(xml_content)
    count = remove_tags_from_xml(root)
    
    assert count == 1
    assert root.find('.//tags') is None
