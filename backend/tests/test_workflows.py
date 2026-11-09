import pytest

from app.workflows import WORKFLOWS, companies, samples


@pytest.mark.parametrize("wf", WORKFLOWS.values(), ids=lambda w: w.key)
def test_definition_is_well_formed(wf):
    keys = [s.key for s in wf.steps]
    assert len(keys) == len(set(keys))
    assert wf.steps[0].key == "intake"
    assert wf.steps[-1].kind == "webhook"
    for i, step in enumerate(wf.steps):
        assert step.max_attempts >= 1
        if step.kind == "review":
            assert step.handler is None
            assert step.review_source in keys[:i]
        else:
            assert step.handler is not None
    assert wf.next_step(keys[-1]) is None
    assert wf.next_step(keys[0]).key == keys[1]


def test_both_workflows_share_the_review_and_webhook_steps():
    for wf in WORKFLOWS.values():
        kinds = [s.kind for s in wf.steps]
        assert kinds[-2:] == ["review", "webhook"]
        assert "llm" in kinds


@pytest.mark.parametrize("key", WORKFLOWS)
def test_samples_are_valid_inputs(key):
    wf = WORKFLOWS[key]
    assert samples()[key]
    for s in samples()[key]:
        wf.input_model.model_validate(s["input"])


def test_lead_samples_point_at_fixture_companies_except_the_failure_case():
    domains = [s["input"]["company_domain"] for s in samples()["lead_outreach"]]
    known = [d for d in domains if d in companies()]
    assert len(known) == len(domains) - 1
    assert "unknown-co.example" not in companies()


def test_fixture_companies_have_signals():
    assert len(companies()) >= 5
    assert all(c.signals for c in companies().values())
