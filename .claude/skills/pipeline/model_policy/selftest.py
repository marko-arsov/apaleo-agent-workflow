"""Portable contract smoke test: python -m model_policy.selftest (no external IO)."""
from datetime import date
from itertools import combinations
from .core import evaluate, resolve_settings, validate_snapshot
from .watch import summarize


def entry(provider, model, lineage, band='strong', rank=10, stages=None, modes=None):
    row = dict(provider=provider, model=model, family=model, lineage=lineage, band=band, rank=rank,
               stages=stages or ['implement-tests', 'implement', 'review'], confidence='reviewed',
               sources=['https://example.invalid/fixture'], reviewed_at='2026-10-29')
    if modes:
        row['modes'] = modes
        row['encoded_effort'] = 'high' if 'demanding' in modes else 'medium'
    return row


def run():
    providers = ['claude', 'codex', 'cursor']
    registry = [dict(provider=p, model=p+'-fixture', family=p, lineage=p, band='strong', rank=10,
                     stages=['implement', 'review'], confidence='reviewed', sources=['https://example.invalid/fixture'],
                     reviewed_at='2026-10-14') for p in providers]
    catalogue = {'providers': {p: {'installed': True, 'models': [{'model': p+'-fixture', 'status': 'advertised'}]} for p in providers}}
    policy = {'test_file_threshold': 4, 'test_line_threshold': 300, 'max_fallbacks': 2,
              'adversary_band_slack': 1, 'adversaries': {'review': ['implement']}}
    cases = 0
    for count in (1, 2, 3):
        for selected in combinations(providers, count):
            settings = resolve_settings([], selected)
            facts = {'stages': ['implement', 'review']}
            result = evaluate(registry, policy, catalogue, settings, facts)
            assert not result['unresolved']
            assert all(r['provider'] in selected for routes in result['routes'].values() for r in routes)
            if count > 1:
                assert result['routes']['review'][0]['provider'] != result['routes']['implement'][0]['provider']
            else:
                assert any(item['reason'] == 'single-lineage' for item in result['advisories'])
            assert result == evaluate(registry, policy, catalogue, settings, facts)
            validate_snapshot(result, result['routes'])
            cases += 1
    spread = [entry('cursor', 'claude-opus-high', 'anthropic', 'deep', modes=['demanding']),
              entry('cursor', 'claude-sonnet-medium', 'anthropic', modes=['balanced']),
              entry('cursor', 'grok-4.7-high', 'xai', modes=['balanced', 'demanding']),
              entry('cursor', 'gpt-5.6-sol-high', 'openai', modes=['balanced', 'demanding'])]
    host = {'installed': True, 'models': [{'model': row['model'], 'status': 'advertised'} for row in spread]}
    tuned = policy | {'adversaries': {'implement-tests': ['implement'], 'review': ['implement', 'implement-tests']}}
    settings = resolve_settings([{'schema_version': 1, 'defaults': {
        'implement': [{'provider': 'cursor', 'model': 'grok-4.7-high'}],
        'review': [{'provider': 'cursor', 'model': 'gpt-5.6-sol-high'}],
    }}], ['cursor'])
    routine = evaluate(spread, tuned, {'providers': {'cursor': host}}, settings,
                       {'stages': ['implement-tests', 'implement', 'review'], 'size': 'medium', 'risk': 'standard'})
    assert [routine['routes'][s][0]['model'] for s in ('implement', 'implement-tests', 'review')] == ['grok-4.7-high', 'claude-sonnet-medium', 'gpt-5.6-sol-high']
    assert not any(item['reason'] == 'adversary-below-band' for item in routine['advisories'])
    demanding = evaluate(spread, tuned, {'providers': {'cursor': host}}, settings,
                         {'stages': ['implement-tests', 'implement', 'review'], 'size': 'large', 'risk': 'high', 'repository_count': 2, 'test_files': 4, 'test_lines': 400})
    assert [demanding['routes'][s][0]['model'] for s in ('implement', 'implement-tests', 'review')] == ['claude-opus-high', 'gpt-5.6-sol-high', 'grok-4.7-high']
    assert {item['stage'] for item in demanding['advisories'] if item['reason'] == 'adversary-below-band'} == {'implement-tests', 'review'}
    pinned = evaluate(spread, policy, {'providers': {'cursor': host}}, resolve_settings([], ['cursor']),
                      {'stages': ['implement', 'review'], 'routes': {'review': [{'provider': 'cursor', 'model': 'claude-opus-high'}]}})
    assert pinned['routes']['review'][0]['model'] == 'claude-opus-high'
    assert pinned['reasons']['review'] == 'explicit-route'
    watched = summarize(
        {},
        {'models': [{'slug': 'grok-4-7-high', 'name': 'Grok 4.7 (High)', 'creator': 'SpaceXAI', 'release_date': '2026-09-21', 'intelligence_index': 35}], 'intelligence_index_version': 5},
        {'routes': [{'provider': 'cursor', 'model': 'grok-4.7-high', 'slug': 'grok-4-7-high'}]},
        {'providers': {'cursor': {'installed': True, 'models': [{'model': 'grok-4.7-high', 'status': 'advertised'}]}}},
        {'implement': [{'provider': 'cursor', 'model': 'missing-model'}]},
        today=date(2026, 10, 29),
    )
    assert watched['baseline'] and watched['routes'][0]['intelligence_index'] == 35 and watched['routes'][0]['advertised']
    assert watched['missing_defaults'][0]['model'] == 'missing-model' and watched['new_slugs'] == []
    cases += 4
    return cases


if __name__ == '__main__':
    print(f'{run()} portable provider-subset contracts passed')
