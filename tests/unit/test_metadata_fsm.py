
import sys
from unittest.mock import MagicMock, patch
from django.db import models
from django.test import TestCase
from rail_django.extensions.metadata import utils

# Mock django_fsm if not present
module_name = 'django_fsm'
if module_name not in sys.modules:
    sys.modules[module_name] = MagicMock()

class MockFSMField:
    pass

class MockTransitionTarget:
    def __init__(self, target):
        self.target = target

class MockFSMMeta:
    def __init__(self, field_name, transitions):
        self.field = MagicMock()
        self.field.name = field_name
        self.transitions = transitions

class FSMTestModel(models.Model):
    state = models.CharField(max_length=50, default='new')

    class Meta:
        app_label = 'test_metadata_v2'

    def get_available_state_transitions(self):
        # This will be mocked or implemented to return available transitions based on state
        if self.state == 'new':
            return [self.publish]
        return []

    def publish(self):
        pass

    # Simulate django-fsm decorator metadata
    publish._django_fsm = MockFSMMeta(
        'state',
        {'new': MockTransitionTarget('published')}
    )

    def archive(self):
        pass

    # Simulate django-fsm decorator metadata
    archive._django_fsm = MockFSMMeta(
        'state',
        {'published': MockTransitionTarget('archived')}
    )

class TestFSMMetadata(TestCase):
    def setUp(self):
        self.model = FSMTestModel

    def test_get_fsm_transitions_static(self):
        """Test retrieving all transitions statically (no instance)."""
        with patch.dict(sys.modules, {'django_fsm': MagicMock()}):
            # We need to ensure the utils module sees our mocked django_fsm
            # Since utils imports it inside the function, patching sys.modules should work

            transitions = utils._get_fsm_transitions(self.model, 'state')

            transition_names = {t['name'] for t in transitions}
            self.assertIn('publish', transition_names)
            self.assertIn('archive', transition_names)

            # Check details of 'publish'
            publish_trans = next(t for t in transitions if t['name'] == 'publish')
            self.assertEqual(publish_trans['source'], ['new'])
            self.assertEqual(publish_trans['target'], 'published')
            # allowed should probably not be present or default to True if we didn't check instance?
            # Looking at code: "allowed": t.get("allowed", True) is in field_extractor,
            # but utils._get_fsm_transitions returns dicts.
            # Let's check what utils returns.
            # It returns dictionaries. In the new code, 'allowed' key might be missing if instance is None?
            # Wait, looking at utils.py code:
            # is_allowed = True
            # if instance: ...
            # "allowed": is_allowed
            # So it should be True.
            self.assertTrue(publish_trans.get('allowed', True))

    def test_get_fsm_transitions_instance_allowed(self):
        """Test retrieving transitions for an instance (allowed)."""
        instance = FSMTestModel(state='new')

        # We need to mock get_available_state_transitions behavior on the instance
        # In the real class above we implemented it simply.

        with patch.dict(sys.modules, {'django_fsm': MagicMock()}):
            transitions = utils._get_fsm_transitions(self.model, 'state', instance=instance)

            publish_trans = next(t for t in transitions if t['name'] == 'publish')
            archive_trans = next(t for t in transitions if t['name'] == 'archive')

            self.assertTrue(publish_trans['allowed'])
            self.assertFalse(archive_trans['allowed'])

    def test_get_fsm_transitions_instance_not_allowed(self):
        """Test retrieving transitions for an instance (not allowed)."""
        instance = FSMTestModel(state='published')

        # Override get_available_state_transitions to simulate 'published' state behavior
        # where 'publish' is not allowed but 'archive' is.
        instance.get_available_state_transitions = lambda: [instance.archive]

        with patch.dict(sys.modules, {'django_fsm': MagicMock()}):
            transitions = utils._get_fsm_transitions(self.model, 'state', instance=instance)

            publish_trans = next(t for t in transitions if t['name'] == 'publish')
            archive_trans = next(t for t in transitions if t['name'] == 'archive')

            self.assertFalse(publish_trans['allowed'])
            self.assertTrue(archive_trans['allowed'])

    @patch('rail_django.extensions.metadata.field_extractor._get_fsm_transitions')
    @patch('rail_django.extensions.metadata.field_extractor._classify_field')
    def test_extract_field_passes_instance(self, mock_classify, mock_get_fsm):
        """Test that _extract_field passes the instance to _get_fsm_transitions."""
        from rail_django.extensions.metadata.field_extractor import FieldExtractorMixin

        extractor = FieldExtractorMixin()
        extractor._map_to_graphql_type = MagicMock(return_value="String")
        extractor._get_python_type = MagicMock(return_value="str")

        mock_classify.return_value = {
            "is_fsm_field": True,
            "is_primary_key": False,
            # Add other required fields to avoid errors if _extract_field uses them
        }

        field = MagicMock(spec=models.Field)
        field.name = 'state'
        field.blank = True
        field.null = True
        field.editable = True
        field.unique = False
        field.is_relation = False
        field.has_default = lambda: False

        # Mock type(field).__name__
        # Since we can't easily mock type() of a mock, we can just let it be MagicMock or ensure FieldExtractor handles it.
        # FieldExtractor uses type(field).__name__.

        instance = FSMTestModel()

        mock_get_fsm.return_value = []

        extractor._extract_field(self.model, field, user=None, instance=instance)

        mock_get_fsm.assert_called_with(self.model, 'state', instance=instance)

