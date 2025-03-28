import os
import uuid
from pathlib import Path
from queue import SimpleQueue
from unittest.mock import MagicMock

import pytest

from ert.config import ErtConfig, ModelConfig
from ert.ensemble_evaluator.snapshot import EnsembleSnapshot
from ert.run_models import BaseRunModel
from ert.storage import Storage
from ert.substitutions import Substitutions


@pytest.fixture(autouse=True)
def patch_abstractmethods(monkeypatch):
    monkeypatch.setattr(BaseRunModel, "__abstractmethods__", set())


class MockJob:
    def __init__(self, status):
        self.status = status


def test_base_run_model_supports_restart(minimum_case):
    brm = BaseRunModel(
        storage=minimum_case,
        runpath_file=MagicMock(),
        user_config_file=MagicMock(),
        env_vars=MagicMock(),
        env_pr_fm_step=MagicMock(),
        model_config=MagicMock(),
        queue_config=minimum_case.queue_config,
        forward_model_steps=MagicMock(),
        status_queue=MagicMock(),
        substitutions=MagicMock(),
        templates=MagicMock(),
        hooked_workflows=MagicMock(),
        active_realizations=[True],
        log_path=Path(""),
    )
    assert brm.support_restart


@pytest.mark.parametrize(
    "initials",
    [
        ([]),
        ([True]),
        ([False]),
        ([False, True]),
        ([True, True]),
        ([False, True]),
    ],
)
def test_active_realizations(initials):
    brm = BaseRunModel(
        storage=MagicMock(),
        runpath_file=MagicMock(),
        user_config_file=MagicMock(),
        env_vars=MagicMock(),
        env_pr_fm_step=MagicMock(),
        model_config=MagicMock(),
        queue_config=MagicMock(),
        forward_model_steps=MagicMock(),
        status_queue=MagicMock(),
        substitutions=MagicMock(),
        templates=MagicMock(),
        hooked_workflows=MagicMock(),
        active_realizations=initials,
        log_path=Path(""),
    )
    brm._initial_realizations_mask = initials
    assert brm.ensemble_size == len(initials)


@pytest.mark.parametrize(
    "initials, completed, any_failed, failures",
    [
        ([True], [False], True, [True]),
        ([False], [False], False, [False]),
        ([False, True], [True, False], True, [False, True]),
        ([False, True], [False, True], False, [False, False]),
        ([False, False], [False, False], False, [False, False]),
        ([False, False], [True, True], False, [False, False]),
        ([True, True], [False, True], True, [True, False]),
        ([False, False], [], True, [True, True]),
    ],
)
def test_failed_realizations(initials, completed, any_failed, failures):
    brm = BaseRunModel(
        storage=MagicMock(),
        runpath_file=MagicMock(),
        user_config_file=MagicMock(),
        env_vars=MagicMock(),
        env_pr_fm_step=MagicMock(),
        model_config=MagicMock(),
        queue_config=MagicMock(),
        forward_model_steps=MagicMock(),
        status_queue=MagicMock(),
        substitutions=MagicMock(),
        templates=MagicMock(),
        hooked_workflows=MagicMock(),
        active_realizations=initials,
        log_path=Path(""),
    )
    brm._initial_realizations_mask = initials
    brm._completed_realizations_mask = completed

    assert brm._create_mask_from_failed_realizations() == failures
    assert brm.has_failed_realizations() == any_failed


@pytest.mark.parametrize(
    "run_path, number_of_iterations, start_iteration, active_realizations_mask, expected",
    [
        ("out/realization-%d/iter-%d", 4, 2, [True, True, True, True], False),
        ("out/realization-%d/iter-%d", 4, 1, [True, True, True, True], True),
        ("out/realization-%d/iter-%d", 4, 1, [False, False, True, False], False),
        ("out/realization-%d/iter-%d", 4, 0, [False, False, False, False], False),
        ("out/realization-%d/iter-%d", 4, 0, [], False),
        ("out/realization-%d", 2, 1, [False, True, True], True),
        ("out/realization-%d", 2, 0, [False, False, True], False),
    ],
)
def test_check_if_runpath_exists(
    create_dummy_run_path,
    run_path: str,
    number_of_iterations: int,
    start_iteration: int,
    active_realizations_mask: list,
    expected: bool,
):
    model_config = ModelConfig(runpath_format_string=run_path)
    subs_list = Substitutions()
    brm = BaseRunModel(
        storage=MagicMock(),
        runpath_file=MagicMock(),
        user_config_file=MagicMock(),
        env_vars=MagicMock(),
        env_pr_fm_step=MagicMock(),
        model_config=model_config,
        queue_config=MagicMock(),
        forward_model_steps=MagicMock(),
        status_queue=MagicMock(),
        substitutions=subs_list,
        templates=MagicMock(),
        hooked_workflows=MagicMock(),
        active_realizations=active_realizations_mask,
        start_iteration=start_iteration,
        total_iterations=number_of_iterations,
        log_path=Path(""),
    )
    assert brm.check_if_runpath_exists() == expected


@pytest.mark.parametrize(
    "active_realizations_mask, expected_number",
    [
        ([True, True, True, True], 2),
        ([False, False, True, True], 0),
        ([True, False, False, True], 1),
    ],
)
def test_get_number_of_existing_runpaths(
    create_dummy_run_path,
    active_realizations_mask,
    expected_number,
):
    run_path = "out/realization-%d/iter-%d"
    model_config = ModelConfig(runpath_format_string=run_path)
    subs_list = Substitutions()
    brm = BaseRunModel(
        storage=MagicMock(),
        runpath_file=MagicMock(),
        user_config_file=MagicMock(),
        env_vars=MagicMock(),
        env_pr_fm_step=MagicMock(),
        model_config=model_config,
        queue_config=MagicMock(),
        forward_model_steps=MagicMock(),
        status_queue=MagicMock(),
        substitutions=subs_list,
        templates=MagicMock(),
        hooked_workflows=MagicMock(),
        active_realizations=active_realizations_mask,
        log_path=Path(""),
    )

    assert brm.get_number_of_existing_runpaths() == expected_number


@pytest.mark.usefixtures("use_tmpdir")
@pytest.mark.parametrize(
    "run_path_format",
    ["<ERTCASE>/realization-<IENS>/iter-<ITER>", "<ERTCASE>/realization-<IENS>"],
)
@pytest.mark.parametrize(
    "active_realizations", [[True], [True, True], [True, False], [False], [False, True]]
)
def test_delete_run_path(run_path_format, active_realizations):
    expected_remaining = []
    expected_removed = []
    for iens, mask in enumerate(active_realizations):
        run_path = Path(
            run_path_format.replace("<IENS>", str(iens))
            .replace("<ITER>", "0")
            .replace("<ERTCASE>", "Case_Name")
        )
        os.makedirs(run_path)
        assert run_path.exists()
        if not mask:
            expected_remaining.append(run_path)
        else:
            expected_removed.append(run_path)
    share_path = Path("share")
    os.makedirs(share_path)
    model_config = ModelConfig(runpath_format_string=run_path_format)
    subs_list = Substitutions({"<ITER>": "0", "<ERTCASE>": "Case_Name"})

    brm = BaseRunModel(
        storage=MagicMock(),
        runpath_file=MagicMock(),
        user_config_file=MagicMock(),
        env_vars=MagicMock(),
        env_pr_fm_step=MagicMock(),
        model_config=model_config,
        queue_config=MagicMock(),
        forward_model_steps=MagicMock(),
        status_queue=MagicMock(),
        substitutions=subs_list,
        templates=MagicMock(),
        hooked_workflows=MagicMock(),
        active_realizations=active_realizations,
        log_path=Path(""),
    )

    brm.rm_run_path()
    assert not any(path.exists() for path in expected_removed)
    assert all(path.parent.exists() for path in expected_removed)
    assert all(path.exists() for path in expected_remaining)
    assert share_path.exists()


def test_num_cpu_is_propagated_from_config_to_ensemble(run_args):
    # Given NUM_CPU in the config file has a special value
    config = ErtConfig.from_file_contents("NUM_REALIZATIONS 2\nNUM_CPU 42")
    # Set up a BaseRunModel object from the config above:

    brm = BaseRunModel(
        storage=MagicMock(spec=Storage),
        runpath_file=MagicMock(),
        user_config_file=MagicMock(),
        env_vars=MagicMock(),
        env_pr_fm_step=MagicMock(),
        model_config=MagicMock(),
        queue_config=config.queue_config,
        forward_model_steps=MagicMock(),
        status_queue=MagicMock(spec=SimpleQueue),
        substitutions=config.substitutions,
        templates=MagicMock(),
        hooked_workflows=MagicMock(),
        active_realizations=[True],
        log_path=Path(""),
    )

    run_args = run_args(config, MagicMock())

    # Instead of running the BaseRunModel, we only test its implementation detail which is to
    # use _build_ensemble() just prior to running
    ensemble = brm._build_ensemble(run_args, uuid.uuid1())

    # Assert the built ensemble has the correct NUM_CPU information
    assert ensemble.reals[0].num_cpu == 42
    assert ensemble.reals[1].num_cpu == 42


@pytest.mark.parametrize(
    "real_status_dict, expected_result",
    [
        pytest.param(
            {"0": "Finished", "1": "Finished", "2": "Finished"},
            {"Finished": 3},
            id="ran_all_realizations_and_all_succeeded",
        ),
        pytest.param(
            {"0": "Finished", "1": "Finished", "2": "Failed"},
            {"Finished": 2, "Failed": 1},
            id="ran_all_realizations_and_some_failed",
        ),
        pytest.param(
            {"0": "Finished", "1": "Running", "2": "Failed"},
            {"Finished": 1, "Failed": 1, "Running": 1},
            id="ran_all_realizations_and_result_was_mixed",
        ),
    ],
)
def test_get_current_status(
    real_status_dict,
    expected_result,
):
    config = ErtConfig.from_file_contents("NUM_REALIZATIONS 3")
    initial_active_realizations = [True] * 3
    new_active_realizations = [True] * 3

    brm = BaseRunModel(
        storage=MagicMock(spec=Storage),
        runpath_file=MagicMock(),
        user_config_file=MagicMock(),
        env_vars=MagicMock(),
        env_pr_fm_step=MagicMock(),
        model_config=MagicMock(),
        queue_config=config.queue_config,
        forward_model_steps=MagicMock(),
        status_queue=MagicMock(spec=SimpleQueue),
        substitutions=config.substitutions,
        templates=MagicMock(),
        hooked_workflows=MagicMock(),
        active_realizations=initial_active_realizations,
        log_path=Path(""),
    )

    snapshot_dict_reals = {}
    for index, realization_status in real_status_dict.items():
        snapshot_dict_reals[index] = {"status": realization_status}
    iter_snapshot = EnsembleSnapshot.from_nested_dict({"reals": snapshot_dict_reals})
    brm._iter_snapshot[0] = iter_snapshot
    brm.active_realizations = new_active_realizations
    assert dict(brm.get_current_status()) == expected_result


@pytest.mark.parametrize(
    "initial_active_realizations, new_active_realizations, real_status_dict, expected_result",
    [
        pytest.param(
            [True, True, True],
            [False, False, False],
            {},
            {"Finished": 3},
            id="all_realizations_in_previous_run_succeeded",
        ),
        pytest.param(
            [True, True, True],
            [False, True, False],
            {},
            {"Finished": 2},
            id="some_realizations_in_previous_run_succeeded",
        ),
        pytest.param(
            [True, True, True],
            [True, True, True],
            {},
            {"Finished": 0},
            id="no_realizations_in_previous_run_succeeded",
        ),
        pytest.param(
            [False, True, True],
            [False, False, True],
            {},
            {"Finished": 1},
            id="did_not_run_all_realizations_and_some_succeeded",
        ),
        pytest.param(
            [False, True, True],
            [False, True, True],
            {},
            {"Finished": 0},
            id="did_not_run_all_realizations_and_none_succeeded",
        ),
        pytest.param(
            [True, True, True],
            [True, True, False],
            {"0": "Finished", "1": "Finished"},
            {"Finished": 3},
            id="reran_some_realizations_and_all_finished",
        ),
        pytest.param(
            [False, True, True],
            [False, True, False],
            {"1": "Finished"},
            {"Finished": 2},
            id="did_not_run_all_realizations_then_reran_and_the_realizations_finished",
        ),
    ],
)
def test_get_current_status_when_rerun(
    initial_active_realizations,
    new_active_realizations,
    real_status_dict: dict[str, str],
    expected_result,
):
    """Active realizations gets changed when we choose to rerun, and the result from the previous run should be included in the current_status."""
    config = ErtConfig.from_file_contents("NUM_REALIZATIONS 3")
    brm = BaseRunModel(
        storage=MagicMock(spec=Storage),
        runpath_file=MagicMock(),
        user_config_file=MagicMock(),
        env_vars=MagicMock(),
        env_pr_fm_step=MagicMock(),
        model_config=MagicMock(),
        queue_config=config.queue_config,
        forward_model_steps=MagicMock(),
        status_queue=MagicMock(spec=SimpleQueue),
        substitutions=config.substitutions,
        templates=MagicMock(),
        hooked_workflows=MagicMock(),
        active_realizations=initial_active_realizations,
        log_path=Path(""),
    )

    brm.restart = True
    snapshot_dict_reals = {}
    for index, realization_status in real_status_dict.items():
        snapshot_dict_reals[index] = {"status": realization_status}
    iter_snapshot = EnsembleSnapshot.from_nested_dict({"reals": snapshot_dict_reals})
    brm._iter_snapshot[0] = iter_snapshot
    brm.active_realizations = new_active_realizations
    assert dict(brm.get_current_status()) == expected_result


def test_get_current_status_for_new_iteration_when_realization_failed_in_previous_run():
    """Active realizations gets changed when we run next iteration, and the failed realizations from
    the previous run should not be present in the current_status."""
    initial_active_realizations = [True] * 5
    # Realization 0,1, and 3 failed in the previous iteration
    new_active_realizations = [False, False, True, False, True]
    config = ErtConfig.from_file_contents("NUM_REALIZATIONS 5")

    brm = BaseRunModel(
        storage=MagicMock(spec=Storage),
        runpath_file=MagicMock(),
        user_config_file=MagicMock(),
        env_vars=MagicMock(),
        env_pr_fm_step=MagicMock(),
        model_config=MagicMock(),
        queue_config=config.queue_config,
        forward_model_steps=MagicMock(),
        status_queue=MagicMock(spec=SimpleQueue),
        substitutions=config.substitutions,
        templates=MagicMock(),
        hooked_workflows=MagicMock(),
        active_realizations=initial_active_realizations,
        log_path=Path(""),
    )

    snapshot_dict_reals = {
        "2": {"status": "Running"},
        "4": {"status": "Finished"},
    }
    iter_snapshot = EnsembleSnapshot.from_nested_dict({"reals": snapshot_dict_reals})
    brm._iter_snapshot[0] = iter_snapshot
    brm.active_realizations = new_active_realizations

    assert brm.restart is False
    assert dict(brm.get_current_status()) == {"Running": 1, "Finished": 1}


@pytest.mark.parametrize(
    "new_active_realizations, was_rerun, expected_result",
    [
        pytest.param(
            [False, False, False, True, False],
            True,
            5,
            id="rerun_so_total_realization_count_is_not_affected_by_previous_failed_realizations",
        ),
        pytest.param(
            [True, True, False, False, False],
            False,
            2,
            id="new_iteration_so_total_realization_count_is_only_previously_successful_realizations",
        ),
    ],
)
def test_get_number_of_active_realizations_varies_when_rerun_or_new_iteration(
    new_active_realizations, was_rerun, expected_result
):
    """When rerunning, we include all realizations in the total amount of active realization.
    When running a new iteration based on the result of the previous iteration, we only include the successful realizations."""
    initial_active_realizations = [True] * 5
    config = ErtConfig.from_file_contents("NUM_REALIZATIONS 5")

    brm = BaseRunModel(
        storage=MagicMock(spec=Storage),
        runpath_file=MagicMock(),
        user_config_file=MagicMock(),
        env_vars=MagicMock(),
        env_pr_fm_step=MagicMock(),
        model_config=MagicMock(),
        queue_config=config.queue_config,
        forward_model_steps=MagicMock(),
        status_queue=MagicMock(spec=SimpleQueue),
        substitutions=config.substitutions,
        templates=MagicMock(),
        hooked_workflows=MagicMock(),
        active_realizations=initial_active_realizations,
        log_path=Path(""),
    )

    brm.active_realizations = new_active_realizations
    brm.restart = was_rerun
    assert brm.get_number_of_active_realizations() == expected_result
