from drift.brain import Brain
from drift.memory import MemoryStream


def test_queued_owner_work_takes_priority_over_optional_planning(tmp_path):
    brain = Brain({'name': 'queue-priority'}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path))
    brain._init_stores()
    brain.thought_count = 1
    brain._cycles_since_plan = Brain.PLAN_INTERVAL
    assert brain.should_plan()
    brain.tasks.create_task('Process the next owner thought', 'Retain its intent')
    assert not brain.should_plan()


def test_capture_contract_preserves_named_systems_and_dependencies(tmp_path):
    import json
    from drift.task import Task
    brain = Brain({'name': 'dependency-retention'}, str(tmp_path))
    task = Task('test', 'Organize an idea', 'Keep its intent',
                source_text='ZOEY remembers through NOESIS but remains distinct from DANNY.')
    instructions, inputs, _ = brain._build_task_context(task)
    assert 'Preserve named systems, dependencies' in instructions
    assert json.loads(inputs[0]['content'])['original_thought_part'] == task.source_text


def test_capture_contract_does_not_promote_a_vision_to_a_verified_capability():
    from drift.capture_context import CAPTURE_INSTRUCTIONS
    assert 'a proposed capability is not an implemented or verified fact' in CAPTURE_INSTRUCTIONS
