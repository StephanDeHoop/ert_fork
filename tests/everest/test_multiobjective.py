import pytest
from ropt.config.enopt import EnOptConfig

from ert.ensemble_evaluator.config import EvaluatorServerConfig
from ert.run_models.everest_run_model import EverestRunModel
from everest.config import EverestConfig
from everest.optimizer.everest2ropt import everest2ropt
from tests.everest.test_config_validation import has_error

CONFIG_FILE = "config_multi_objectives.yml"


def test_config_multi_objectives(copy_mocked_test_data_to_tmp):
    config = EverestConfig.load_file(CONFIG_FILE)
    config_dict = config.to_dict()

    obj_funcs = config_dict["objective_functions"]
    assert len(obj_funcs) == 2

    obj_funcs[0]["weight"] = 1.0
    assert has_error(
        EverestConfig.lint_config_dict(config_dict),
        match="Weight should be given either for all of the"
        " objectives or for none of them",
    )  # weight given only for some obj

    obj_funcs[1]["weight"] = 3
    assert (
        len(EverestConfig.lint_config_dict(config_dict)) == 0
    )  # weight given for all the objectivs

    obj_funcs.append({"weight": 1, "scale": 1})
    assert has_error(
        EverestConfig.lint_config_dict(config_dict),
        match="Field required",
    )  # no name

    obj_funcs[-1]["name"] = " test_obj"
    obj_funcs[-1]["weight"] = -0.3
    assert has_error(
        EverestConfig.lint_config_dict(config_dict),
        match="Input should be greater than 0",
    )  # negative weight

    obj_funcs[-1]["weight"] = 0
    assert has_error(
        EverestConfig.lint_config_dict(config_dict),
        match="Input should be greater than 0",
    )  # 0 weight

    obj_funcs[-1]["weight"] = 1
    obj_funcs[-1]["scale"] = 0
    assert has_error(
        EverestConfig.lint_config_dict(config_dict),
        match="Scale value cannot be zero",
    )  # 0 scale

    obj_funcs[-1]["scale"] = -125
    assert (
        len(EverestConfig.lint_config_dict(config_dict)) == 0
    )  # negative normalization is ok)

    obj_funcs.pop()
    assert len(EverestConfig.lint_config_dict(config_dict)) == 0

    # test everest initialization
    EverestRunModel.create(config)


def test_multi_objectives2ropt(copy_mocked_test_data_to_tmp):
    config = EverestConfig.load_file(CONFIG_FILE)
    config_dict = config.to_dict()
    ever_objs = config_dict["objective_functions"]
    ever_objs[0]["weight"] = 1.33
    ever_objs[1]["weight"] = 3.1
    assert len(EverestConfig.lint_config_dict(config_dict)) == 0

    norm = ever_objs[0]["weight"] + ever_objs[1]["weight"]

    enopt_config = EnOptConfig.model_validate(
        everest2ropt(EverestConfig.model_validate(config_dict))
    )
    assert len(enopt_config.objectives.weights) == 2
    assert enopt_config.objectives.weights[1] == ever_objs[1]["weight"] / norm
    assert enopt_config.objectives.weights[0] == ever_objs[0]["weight"] / norm


@pytest.mark.integration_test
def test_multi_objectives_run(copy_mocked_test_data_to_tmp):
    config = EverestConfig.load_file(CONFIG_FILE)
    run_model = EverestRunModel.create(config)
    evaluator_server_config = EvaluatorServerConfig()
    run_model.run_experiment(evaluator_server_config)
