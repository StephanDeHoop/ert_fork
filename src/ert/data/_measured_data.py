"""
Read-only API to fetch responses (a.k.a measurements) and
matching observations from internal ERT-storage.
The main goal is to facilitate data-analysis using scipy and similar tools,
instead of having to implement analysis-functionality into ERT using C/C++.
The API is typically meant used as part of workflows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from ert.storage import Ensemble


class ResponseError(Exception):
    pass


class MeasuredData:
    def __init__(
        self,
        ensemble: Ensemble,
        keys: list[str] | None = None,
    ) -> None:
        if keys is None:
            keys = sorted(ensemble.experiment.observation_keys)
        if not keys:
            raise ObservationError("No observation keys provided")

        self._set_data(self._get_data(ensemble, keys))

    @property
    def data(self) -> pd.DataFrame:
        return self._data

    def _set_data(self, data: pd.DataFrame) -> None:
        expected_keys = {"OBS", "STD"}
        if not isinstance(data, pd.DataFrame):
            raise TypeError(
                f"Invalid type: {type(data)}, should be type: {pd.DataFrame}"
            )
        if not expected_keys.issubset(data.index):
            missing = expected_keys - set(data.index)
            raise ValueError(
                f"{expected_keys} should be present in DataFrame index, \
                missing: {missing}"
            )
        self._data = data

    def remove_failed_realizations(self) -> None:
        """Removes rows with no simulated data, leaving observations and
        standard deviations as-is."""
        pre_index = self.data.index
        post_index = list(self.data.dropna(axis=0, how="all").index)
        drop_index = set(pre_index) - {*post_index, "STD", "OBS"}
        self._set_data(self.data.drop(index=drop_index))

    def get_simulated_data(self) -> pd.DataFrame:
        """Dimension of data is (number of responses x number of realizations)."""
        return self.data[~self.data.index.isin(["OBS", "STD"])]

    def remove_inactive_observations(self) -> None:
        """Removes columns with one or more NaN or inf values."""
        filtered_dataset = self.data.replace([np.inf, -np.inf], np.nan).dropna(
            axis="columns", how="any"
        )
        if filtered_dataset.empty:
            raise ValueError(
                "This operation results in an empty dataset "
                "(could be due to one or more failed realizations)"
            )
        self._set_data(filtered_dataset)

    def is_empty(self) -> bool:
        return bool(self.data.empty)

    @staticmethod
    def _get_data(
        ensemble: Ensemble,
        observed_response_keys: list[str],
    ) -> pd.DataFrame:
        """
        Adds simulated and observed data and returns a dataframe where ensemble
        members will have a data key, observed data will be named OBS and
        observed standard deviation will be named STD.
        """

        resp_key_to_resp_type = ensemble.experiment.response_key_to_response_type
        selected_response_types = {
            response_type
            for response_key, response_type in resp_key_to_resp_type.items()
            if response_key in observed_response_keys
        }

        active_realizations = ensemble.get_realization_list_with_responses()

        # Check if responses exist for all selected response types
        for response_type in selected_response_types:
            df = ensemble.load_responses(response_type, tuple(active_realizations))
            if df.is_empty():
                raise ResponseError(
                    f"No response loaded for observation type: {response_type}"
                )

        df = (
            ensemble.get_observations_and_responses(
                observed_response_keys, np.array(active_realizations)
            )
            .rename(
                {
                    "index": "key_index",
                    "observations": "OBS",
                    "std": "STD",
                }
            )
            .select(
                "key_index",
                "response_key",
                "observation_key",
                "OBS",
                "STD",
                *map(str, active_realizations),
            )
            .sort(by="observation_key")
        )

        pddf = df.to_pandas()[
            [
                "observation_key",
                "key_index",
                "OBS",
                "STD",
                *df.columns[5:],
            ]
        ]

        # Pandas differentiates vs int and str keys.
        # Legacy-wise we use int keys for realizations
        pddf.rename(
            columns={str(k): int(k) for k in active_realizations},
            inplace=True,
        )

        pddf = pddf.set_index(["observation_key", "key_index"]).transpose()

        return pddf


class ObservationError(Exception):
    pass
