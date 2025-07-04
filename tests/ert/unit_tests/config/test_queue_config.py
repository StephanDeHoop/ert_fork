import logging
import warnings

import hypothesis.strategies as st
import pytest
from hypothesis import given
from pydantic import ValidationError

from ert.config import (
    ConfigValidationError,
    ConfigWarning,
    ErtConfig,
    QueueConfig,
    QueueSystem,
)
from ert.config.parsing import ConfigKeys
from ert.config.queue_config import (
    LocalQueueOptions,
    LsfQueueOptions,
    SlurmQueueOptions,
    TorqueQueueOptions,
)
from ert.scheduler import LocalDriver, LsfDriver, OpenPBSDriver, SlurmDriver


def test_create_local_copy_is_a_copy_with_local_queue_system():
    queue_config = QueueConfig(queue_system=QueueSystem.LSF)
    assert queue_config.queue_system == QueueSystem.LSF
    local_queue_config = queue_config.create_local_copy()
    assert local_queue_config.queue_system == QueueSystem.LOCAL
    assert isinstance(local_queue_config.queue_options, LocalQueueOptions)


@pytest.mark.parametrize("value", [True, False])
def test_stop_long_running_is_set_from_corresponding_keyword(value):
    assert (
        QueueConfig.from_dict({ConfigKeys.STOP_LONG_RUNNING: value}).stop_long_running
        == value
    )
    assert QueueConfig(stop_long_running=value).stop_long_running == value


@pytest.mark.parametrize("queue_system", ["LSF", "TORQUE", "SLURM"])
def test_project_code_is_set_when_forward_model_contains_selected_simulator(
    queue_system,
):
    queue_config = QueueConfig.from_dict(
        {
            ConfigKeys.FORWARD_MODEL: [("FLOW",), ("RMS",)],
            ConfigKeys.QUEUE_SYSTEM: queue_system,
        }
    )
    project_code = queue_config.queue_options.project_code

    assert project_code is not None
    assert "flow" in project_code
    assert "rms" in project_code


@pytest.mark.parametrize(
    "queue_system", [QueueSystem.LSF, QueueSystem.TORQUE, QueueSystem.SLURM]
)
def test_project_code_is_not_overwritten_if_set_in_config(queue_system):
    queue_config = QueueConfig.from_dict(
        {
            ConfigKeys.FORWARD_MODEL: [("FLOW",), ("RMS",)],
            ConfigKeys.QUEUE_SYSTEM: queue_system,
            "QUEUE_OPTION": [
                [queue_system, "PROJECT_CODE", "test_code"],
            ],
        }
    )
    assert queue_config.queue_options.project_code == "test_code"


@pytest.mark.parametrize("invalid_queue_system", ["VOID", "BLABLA", "GENERIC", "*"])
def test_that_an_invalid_queue_system_provided_raises_validation_error(
    invalid_queue_system,
):
    """There is actually a "queue-system" called GENERIC, but it is
    only there for making queue options global, it should not be
    possible to try to use it"""
    with pytest.raises(
        expected_exception=ConfigValidationError,
        match=(
            f"'QUEUE_SYSTEM' argument 1 must be one of .* was '{invalid_queue_system}'"
        ),
    ):
        ErtConfig.from_file_contents(
            f"NUM_REALIZATIONS 1\nQUEUE_SYSTEM {invalid_queue_system}\n"
        )


@pytest.mark.parametrize(
    "queue_system, invalid_option",
    [(QueueSystem.LOCAL, "BSUB_CMD"), (QueueSystem.TORQUE, "BOGUS")],
)
def test_that_invalid_queue_option_raises_validation_error(
    queue_system, invalid_option
):
    with pytest.raises(
        expected_exception=ConfigValidationError,
        match=f"Invalid QUEUE_OPTION for {queue_system}: '{invalid_option}'",
    ):
        _ = ErtConfig.from_file_contents(
            f"NUM_REALIZATIONS 1\nQUEUE_SYSTEM {queue_system}\n"
            f"QUEUE_OPTION {queue_system} {invalid_option}"
        )


@st.composite
def memory_with_unit(draw):
    memory_value = draw(st.integers(min_value=1, max_value=10000))
    unit = draw(
        st.sampled_from(["gb", "mb", "tb", "pb", "Kb", "Gb", "Mb", "Pb", "b", "B", ""])
    )
    return f"{memory_value}{unit}"


@given(memory_with_unit())
def test_supported_memory_units_to_realization_memory(
    memory_with_unit,
):
    assert (
        ErtConfig.from_file_contents(
            f"NUM_REALIZATIONS 1\nREALIZATION_MEMORY {memory_with_unit}\n"
        ).queue_config.queue_options.realization_memory
        > 0
    )


@pytest.mark.parametrize(
    "memory_spec, expected_bytes",
    [
        ("1", 1),
        ("1b", 1),
        ("10b", 10),
        ("10kb", 10 * 1024),
        ("10mb", 10 * 1024**2),
        ("10gb", 10 * 1024**3),
        ("10Mb", 10 * 1024**2),
        ("10Gb", 10 * 1024**3),
        ("10Tb", 10 * 1024**4),
        ("10Pb", 10 * 1024**5),
    ],
)
def test_realization_memory_unit_support(memory_spec: str, expected_bytes: int):
    assert (
        ErtConfig.from_file_contents(
            f"NUM_REALIZATIONS 1\nREALIZATION_MEMORY {memory_spec}\n"
        ).queue_config.queue_options.realization_memory
        == expected_bytes
    )


@pytest.mark.parametrize(
    "invalid_memory_spec, error_message",
    [
        ("-1", "Negative memory does not make sense in -1"),
        ("-1b", "Negative memory does not make sense in -1b"),
        ("b", "Could not understand byte unit in b"),
        ("4ub", "Could not understand byte unit in 4ub"),
    ],
)
def test_invalid_realization_memory(invalid_memory_spec: str, error_message: str):
    with pytest.raises(
        ConfigValidationError, match=rf"Line 2 \(Column \d+-\d+\): {error_message}"
    ):
        ErtConfig.from_file_contents(
            f"NUM_REALIZATIONS 1\nREALIZATION_MEMORY {invalid_memory_spec}\n"
        )


@pytest.mark.parametrize(
    "queue_system, queue_system_option",
    [
        (QueueSystem.LSF, "LSF_QUEUE"),
        (QueueSystem.SLURM, "SQUEUE"),
        (QueueSystem.TORQUE, "QUEUE"),
    ],
)
def test_that_overwriting_QUEUE_OPTIONS_warns(
    queue_system, queue_system_option, caplog
):
    with caplog.at_level(logging.INFO):
        ErtConfig.from_file_contents(
            user_config_contents="NUM_REALIZATIONS 1\n"
            f"QUEUE_SYSTEM {queue_system}\n"
            f"QUEUE_OPTION {queue_system} {queue_system_option} test_1\n"
            f"QUEUE_OPTION {queue_system} MAX_RUNNING 10\n",
            site_config_contents="JOB_SCRIPT fm_dispatch.py\n"
            f"QUEUE_SYSTEM {queue_system}\n"
            f"QUEUE_OPTION {queue_system} {queue_system_option} test_0\n"
            f"QUEUE_OPTION {queue_system} MAX_RUNNING 10\n",
        )
    assert (
        f"Overwriting QUEUE_OPTION {queue_system} {queue_system_option}: \n Old value:"
        " test_0 \n New value: test_1"
    ) in caplog.text
    assert (
        f"Overwriting QUEUE_OPTION {queue_system} MAX_RUNNING: \n Old value:"
        " 10 \n New value: 10"
    ) not in caplog.text


@pytest.mark.parametrize(
    "queue_system, queue_system_option",
    [("LSF", "LSF_QUEUE"), ("SLURM", "SQUEUE")],
)
def test_initializing_empty_config_queue_options_resets_to_default_value(
    queue_system, queue_system_option
):
    config_object = ErtConfig.from_file_contents(
        "NUM_REALIZATIONS 1\n"
        f"QUEUE_SYSTEM {queue_system}\n"
        f"QUEUE_OPTION {queue_system} {queue_system_option}\n"
        f"QUEUE_OPTION {queue_system} MAX_RUNNING\n"
    )

    if queue_system == "LSF":
        assert config_object.queue_config.queue_options.lsf_queue is None
    if queue_system == "SLURM":
        assert config_object.queue_config.queue_options.squeue == "squeue"
    assert config_object.queue_config.queue_options.max_running == 0


@pytest.mark.parametrize(
    "queue_system, queue_option, queue_value, err_msg",
    [
        ("SLURM", "SQUEUE_TIMEOUT", "5a", "should be a valid number"),
    ],
)
def test_wrong_config_option_types(queue_system, queue_option, queue_value, err_msg):
    file_contents = (
        "NUM_REALIZATIONS 1\n"
        f"QUEUE_SYSTEM {queue_system}\n"
        f"QUEUE_OPTION {queue_system} {queue_option} {queue_value}\n"
    )

    with pytest.raises(ConfigValidationError, match=err_msg):
        ErtConfig.from_file_contents(file_contents)


def test_that_configuring_another_queue_system_gives_warning():
    with pytest.warns(ConfigWarning, match="should be a valid number"):
        ErtConfig.from_file_contents(
            "NUM_REALIZATIONS 1\n"
            "QUEUE_SYSTEM LSF\n"
            "QUEUE_OPTION SLURM SQUEUE_TIMEOUT ert\n"
        )


def test_max_running_property():
    config = ErtConfig.from_file_contents(
        "NUM_REALIZATIONS 1\n"
        "QUEUE_SYSTEM TORQUE\n"
        "QUEUE_OPTION TORQUE MAX_RUNNING 17\n"
        "QUEUE_OPTION TORQUE MAX_RUNNING 19\n"
        "QUEUE_OPTION LOCAL MAX_RUNNING 11\n"
        "QUEUE_OPTION LOCAL MAX_RUNNING 13\n"
    )

    assert config.queue_config.queue_system == QueueSystem.TORQUE
    assert config.queue_config.max_running == 19


@pytest.mark.parametrize("queue_system", ["LSF", "GENERIC"])
def test_multiple_submit_sleep_keywords(queue_system):
    with warnings.catch_warnings(record=True) as all_warnings:
        config = ErtConfig.from_file_contents(
            "NUM_REALIZATIONS 1\n"
            "QUEUE_SYSTEM LSF\n"
            "QUEUE_OPTION LSF SUBMIT_SLEEP 10\n"
            f"QUEUE_OPTION {queue_system} SUBMIT_SLEEP 42\n"
            "QUEUE_OPTION TORQUE SUBMIT_SLEEP 22\n"
        )
        assert config.queue_config.submit_sleep == 42
        assert len(all_warnings) > 0
        assert all(issubclass(w.category, ConfigWarning) for w in all_warnings)
        assert all(
            str(w.message)
            == (
                "The SUBMIT_SLEEP keyword in QUEUE_OPTION is deprecated. "
                "Put SUBMIT_SLEEP <seconds> on a separate line instead"
            )
            for w in all_warnings
        )


def test_multiple_submit_sleep_keywords_without_queue_system():
    with warnings.catch_warnings(record=True) as all_warnings:
        config = ErtConfig.from_file_contents("NUM_REALIZATIONS 1\nSUBMIT_SLEEP 3\n")
        assert config.queue_config.submit_sleep == 3
        assert len(all_warnings) == 0


def test_multiple_max_submit_keywords():
    assert (
        ErtConfig.from_file_contents(
            "NUM_REALIZATIONS 1\nMAX_SUBMIT 10\nMAX_SUBMIT 42\n"
        ).queue_config.max_submit
        == 42
    )


@pytest.mark.parametrize(
    "max_submit_value, error_msg",
    [
        (-1, "must have a positive integer value as argument"),
        (0, "must have a positive integer value as argument"),
        (1.5, "must have an integer value as argument"),
    ],
)
def test_wrong_max_submit_raises_validation_error(max_submit_value, error_msg):
    with pytest.raises(ConfigValidationError, match=error_msg):
        ErtConfig.from_file_contents(
            f"NUM_REALIZATIONS 1\nMAX_SUBMIT {max_submit_value}\n"
        )


@pytest.mark.parametrize(
    "queue_system, key, value",
    [
        ("LSF", "MAX_RUNNING", 50),
        ("SLURM", "MAX_RUNNING", 50),
        ("TORQUE", "MAX_RUNNING", 50),
        ("LSF", "SUBMIT_SLEEP", 4.2),
        ("SLURM", "SUBMIT_SLEEP", 4.2),
        ("TORQUE", "SUBMIT_SLEEP", 4.2),
    ],
)
def test_global_queue_options(queue_system, key, value):
    def _check_results(contents):
        ert_config = ErtConfig.from_file_contents(contents)
        if key == "MAX_RUNNING":
            assert ert_config.queue_config.max_running == value
        elif key == "SUBMIT_SLEEP":
            assert ert_config.queue_config.submit_sleep == value
        else:
            raise KeyError("Unexpected key")

    _check_results(
        "NUM_REALIZATIONS 1\n"
        f"QUEUE_SYSTEM {queue_system}\n"
        f"QUEUE_OPTION {queue_system} {key} 10\n"
        f"QUEUE_OPTION GENERIC {key} {value}\n"
    )

    _check_results(f"NUM_REALIZATIONS 1\nQUEUE_SYSTEM {queue_system}\n{key} {value}\n")


@pytest.mark.parametrize(
    "queue_system, key, value",
    [
        ("LSF", "MAX_RUNNING", 50),
        ("SLURM", "MAX_RUNNING", 50),
        ("TORQUE", "MAX_RUNNING", 50),
        ("LSF", "SUBMIT_SLEEP", 4.2),
        ("SLURM", "SUBMIT_SLEEP", 4.2),
        ("TORQUE", "SUBMIT_SLEEP", 4.2),
    ],
)
def test_global_config_key_does_not_overwrite_queue_options(queue_system, key, value):
    def _check_results(contents):
        ert_config = ErtConfig.from_file_contents(contents)
        if key == "MAX_RUNNING":
            assert ert_config.queue_config.max_running == value
        elif key == "SUBMIT_SLEEP":
            assert ert_config.queue_config.submit_sleep == value
        else:
            raise KeyError("Unexpected key")

    _check_results(
        "NUM_REALIZATIONS 1\n"
        f"QUEUE_SYSTEM {queue_system}\n"
        f"QUEUE_OPTION {queue_system} {key} {value}\n"
        f"{key} {value + 42}\n"
    )

    _check_results(
        "NUM_REALIZATIONS 1\n"
        f"QUEUE_SYSTEM {queue_system}\n"
        f"QUEUE_OPTION GENERIC {key} {value}\n"
        f"{key} {value + 42}\n"
    )


def test_negative_submit_sleep_raises_validation_error():
    with pytest.raises(
        ValidationError, match="Input should be greater than or equal to 0"
    ):
        ErtConfig.from_file_contents("NUM_REALIZATIONS 1\nSUBMIT_SLEEP -4.2\n")


@pytest.mark.parametrize(
    "queue_system, key, value",
    [
        ("LSF", "MAX_RUNNING", -50),
        ("SLURM", "MAX_RUNNING", -50),
        ("TORQUE", "MAX_RUNNING", -50),
        ("LSF", "SUBMIT_SLEEP", -4.2),
        ("SLURM", "SUBMIT_SLEEP", -4.2),
        ("TORQUE", "SUBMIT_SLEEP", -4.2),
    ],
)
def test_wrong_generic_queue_option_raises_validation_error(queue_system, key, value):
    with pytest.raises(
        ConfigValidationError,
        match=f"Input should be greater than or equal to 0. Got input '{value}'",
    ):
        ErtConfig.from_file_contents(
            "NUM_REALIZATIONS 1\n"
            f"QUEUE_SYSTEM {queue_system}\n"
            f"QUEUE_OPTION GENERIC {key} {value}\n"
        )

    if key == "SUBMIT_SLEEP":
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 0"
        ):
            ErtConfig.from_file_contents(
                f"NUM_REALIZATIONS 1\nQUEUE_SYSTEM {queue_system}\n{key} {value}\n"
            )
    else:
        with pytest.raises(
            ConfigValidationError, match="must have a positive integer value"
        ):
            ErtConfig.from_file_contents(
                f"NUM_REALIZATIONS 1\nQUEUE_SYSTEM {queue_system}\n{key} {value}\n"
            )


@pytest.mark.parametrize(
    "queue_system",
    (QueueSystem.LSF, QueueSystem.TORQUE, QueueSystem.LOCAL, QueueSystem.SLURM),
)
def test_driver_initialization_from_defaults(queue_system):
    if queue_system == QueueSystem.LSF:
        LsfDriver(**LsfQueueOptions().driver_options)
    if queue_system == QueueSystem.TORQUE:
        OpenPBSDriver(**TorqueQueueOptions().driver_options)
    if queue_system == QueueSystem.LOCAL:
        LocalDriver(**LocalQueueOptions().driver_options)
    if queue_system == QueueSystem.SLURM:
        SlurmDriver(**SlurmQueueOptions().driver_options)


@pytest.mark.parametrize(
    "venv, expected", [("my_env", "source my_env/bin/activate"), (None, "")]
)
def test_default_activate_script_generation(expected, monkeypatch, venv):
    if venv:
        monkeypatch.setenv("VIRTUAL_ENV", venv)
    else:
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    options = LocalQueueOptions()
    assert options.activate_script == expected


@pytest.mark.parametrize(
    "env, expected",
    [
        ("my_env", 'eval "$(conda shell.bash hook)" && conda activate my_env'),
    ],
)
def test_conda_activate_script_generation(expected, monkeypatch, env):
    monkeypatch.setenv("VIRTUAL_ENV", "")
    monkeypatch.setenv("CONDA_ENV", env)
    options = LocalQueueOptions(name="local")
    assert options.activate_script == expected


@pytest.mark.parametrize(
    "env, expected",
    [("my_env", "source my_env/bin/activate")],
)
def test_multiple_activate_script_generation(expected, monkeypatch, env):
    monkeypatch.setenv("VIRTUAL_ENV", env)
    monkeypatch.setenv("CONDA_ENV", env)
    options = LocalQueueOptions(name="local")
    assert options.activate_script == expected


def test_default_max_runtime_is_unlimited():
    assert QueueConfig.from_dict({}).max_runtime is None
    assert QueueConfig().max_runtime is None


@given(st.integers(min_value=1))
def test_max_runtime_is_set_from_corresponding_keyword(value):
    assert QueueConfig.from_dict({ConfigKeys.MAX_RUNTIME: value}).max_runtime == value
    assert QueueConfig(max_runtime=value).max_runtime == value


def test_that_job_script_from_queue_options_takes_precedence_over_global(
    copy_poly_case,
):
    config = ErtConfig.from_file_contents(
        "NUM_REALIZATIONS 1\n"
        "JOB_SCRIPT poly_eval.py\n"
        "QUEUE_SYSTEM LSF\n"
        "QUEUE_OPTION LSF JOB_SCRIPT fm_dispatch_lsf.py\n"
    )
    assert config.queue_config.queue_options.job_script == "fm_dispatch_lsf.py"
