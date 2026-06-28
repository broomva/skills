"""Device value object — identifies the producer of a sample."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Device"]


class Device(BaseModel):
    """A wearable / sensor / app that produced a sample.

    Frozen, fully optional except `manufacturer`. Empty fields are tolerated
    because many adapters return only partial device metadata.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    manufacturer: str = Field(..., description="e.g. 'garmin', 'apple', 'whoop'")
    product: str | None = Field(default=None, description="e.g. 'fenix 7x sapphire solar'")
    hardware_id: str | None = Field(default=None, description="serial / device ID")
    software_version: str | None = Field(default=None, description="firmware / app version")
