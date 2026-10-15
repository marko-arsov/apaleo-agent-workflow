"""Model snapshots remain independent from refreshed defaults and other workflows."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_manifest as fixtures
import pipeline_manifest as manifest
import model_routing
from model_policy import core
from model_policy.storage import read, write


class RoutingTests(unittest.TestCase):
    def test_snapshot_creation_historical_validation_and_override(self):
        kwargs=fixtures.ManifestTests()._make_kwargs()
        original=manifest.make_manifest(**kwargs)
        routes={s['name']:[s['route'],*s.get('fallbacks',[])] for s in original['stages'] if s.get('selected') and s['name'] in manifest.AI_STAGES}
        registry=read(Path(core.__file__).with_name('registry.json'))
        policy=read(Path(core.__file__).with_name('policy.json'))
        selection=core.evaluate(registry,policy,{},core.resolve_settings([],core.PROVIDERS),{'stages':list(routes),'routes':routes})
        new=manifest.make_manifest(**kwargs,model_selection=selection)
        self.assertFalse(manifest.validate(new))
        with patch.object(manifest,'REVIEW_SUGGESTIONS',{}),patch.object(manifest,'DEFAULT_ROUTES',{}):
            self.assertFalse(manifest.validate(new))
        changed=copy.deepcopy(new);changed['stages'][1]['route']['model']='changed'
        self.assertTrue(manifest.validate(changed))
        overridden=manifest.runtime_manifest(new,route_assignments=['implement=codex:chosen:medium'])
        self.assertIn('original_model_selection',overridden)
        self.assertNotIn('model_selection',overridden)
        self.assertEqual(new['model_selection'],selection)

    def test_independent_store_defaults_without_real_user_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.dict(os.environ,{'HOME':str(root/'home'),'XDG_DATA_HOME':str(root/'data')},clear=True):
                store=model_routing.store(root)
                result=store.evaluate({'stages':['implement']})
                self.assertEqual(result['routes']['implement'],[manifest.DEFAULT_ROUTES['implement']])
                proposal=store.propose({'global':{'schema_version':1,'providers':['codex']}},'global')
                store.apply(proposal,proposal['approval'])
                self.assertFalse((root/'data/agent-workflow').exists())
                self.assertEqual(store.effective()['providers'],['codex'])

    def test_explicit_assignment_conflicts_require_new_snapshot(self):
        kwargs=fixtures.ManifestTests()._make_kwargs(tests=False)
        routes={name:[dict(provider='codex',model='chosen',reasoning='medium')] for name in ['implement','review']}
        kwargs['stages']=['implement','review']
        selection=core.evaluate([],read(Path(core.__file__).with_name('policy.json')),{},core.resolve_settings([],['codex']),{'stages':list(routes),'routes':routes})
        kwargs['route_assignments']=['implement=codex:different:medium']
        with self.assertRaises(manifest.ManifestError):manifest.make_manifest(**kwargs,model_selection=selection)

    def test_provider_commands_do_not_inject_high_when_effort_is_missing(self):
        import implement_pipeline as runner
        with patch.object(runner, 'find_codex', return_value='codex'), patch.object(runner, 'find_claude', return_value='claude'):
            for provider in ('codex', 'claude'):
                route = {'provider':provider, 'model':'chosen'}
                initial = runner.provider_command(route, 'prompt', Path('/tmp/unused-model-output'))
                resumed = runner.provider_resume_command(route, 'session', 'prompt', Path('/tmp/unused-model-output'))
                for argv in (initial, resumed):
                    self.assertNotIn('--effort',argv)
                    self.assertFalse(any('model_reasoning_effort' in part for part in argv))
