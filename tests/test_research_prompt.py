import json

from drift.research_prompt import research_prompt


def test_prompt_is_valid_bounded_json_and_retains_source_identifiers():
    retained = ('Navigation ' * 700) + 'Errors detected during execution are called exceptions.'
    session = {'query': 'What are errors detected during execution called?', 'sources': [
        {'id': 'source-1', 'url': 'https://example.com/docs', 'text': retained}]}
    instructions, items = research_prompt(session, 5000)
    assert len(instructions) + len(json.dumps(items, ensure_ascii=False)) <= 5000
    payload = json.loads(items[0]['content'])
    assert payload['sources'][0]['source_id'] == 'source-1'
    assert any('called exceptions' in snippet for snippet in payload['sources'][0]['snippets'])
    assert all(snippet in retained for snippet in payload['sources'][0]['snippets'])
    assert 'JSON' in instructions
    assert 'source_id' in instructions


def test_multiple_large_sources_do_not_break_json_or_leak_credentials():
    session = {'query': 'Compare research evidence', 'sources': [
        {'id': f'source-{i}', 'url': 'https://example.com',
         'text': 'password="synthetic multiword value"\n' + ('Research evidence ' * 1000)}
        for i in range(10)]}
    instructions, items = research_prompt(session, 3500)
    encoded = json.dumps(items, ensure_ascii=False)
    assert len(instructions) + len(encoded) <= 3500
    assert json.loads(items[0]['content'])['sources']
    assert 'synthetic multiword value' not in encoded


def test_tiny_context_fails_closed_instead_of_cutting_json():
    import pytest
    with pytest.raises(ValueError, match='research context'):
        research_prompt({'query': 'question', 'sources': []}, 40)
