from pydantic import BaseModel, Field, field_validator

from everest.config.validation_utils import check_writable_filepath


class ExportConfig(BaseModel, extra="forbid"):
    csv_output_filepath: str | None = Field(
        default=None,
        description="""Specifies which file to write the export to.
        Defaults to <config_file_name>.csv in output folder.""",
    )
    discard_gradient: bool | None = Field(
        default=None,
        description="If set to True, Everest export will not contain "
        "gradient simulation data.",
    )
    discard_rejected: bool | None = Field(
        default=None,
        description="""If set to True, Everest export will contain only simulations
         that have the increase_merit flag set to true.""",
    )
    keywords: list[str] | None = Field(
        default=None,
        description="List of eclipse keywords to be exported into csv.",
    )
    batches: list[int] | None = Field(
        default=None,
        description="list of batches to be exported, default is all batches.",
    )
    skip_export: bool | None = Field(
        default=None,
        description="""set to True if export should not
                     be run after the optimization case.
                     Default value is False.""",
    )

    @field_validator("csv_output_filepath", mode="before")
    @classmethod
    def validate_output_file_writable(cls, csv_output_filepath: str | None) -> str:
        if csv_output_filepath is None:
            raise ValueError("csv_output_filepath can not be None")
        check_writable_filepath(csv_output_filepath)
        return csv_output_filepath
