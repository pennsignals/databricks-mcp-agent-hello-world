from __future__ import annotations

import pyarrow as pa
import pytest
from pydantic import BaseModel

from databricks_tool_agent_template.storage import schema


def test_arrow_field_to_spark_sql_type_rejects_unsupported_arrow_type() -> None:
    with pytest.raises(ValueError, match="Unsupported Arrow type"):
        schema.arrow_field_to_spark_sql_type(pa.field("bad", pa.bool_(), nullable=False))


def test_safe_jsonable_supports_model_and_mapping_like_payloads() -> None:
    class ModelDumpPayload(BaseModel):
        value: str = "model"

    class AsDictPayload:
        def as_dict(self) -> object:
            return {"value": "as_dict"}

    class DictPayload:
        def dict(self) -> object:
            return {"value": "dict"}

    assert schema.safe_jsonable(ModelDumpPayload()) == {"value": "model"}
    assert schema.safe_jsonable(AsDictPayload()) == {"value": "as_dict"}
    assert schema.safe_jsonable(DictPayload()) == {"value": "dict"}
    assert schema.safe_jsonable({1: {"nested": {1, 2}}})["1"]["nested"] in ([1, 2], [2, 1])


def test_validate_event_rows_accepts_serialized_event_rows() -> None:
    assert (
        schema.validate_event_rows(
            [
                schema.serialize_event_row(
                    run_key="run-1",
                    task_name="task",
                    event_index=0,
                    event_type="started",
                    payload={"ok": True},
                )
            ]
        ).num_rows
        == 1
    )
