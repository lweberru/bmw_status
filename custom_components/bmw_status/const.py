"""Constants for BMW Status."""

from typing import Final

DOMAIN: Final = "bmw_status"
CARDATA_DOMAIN: Final = "cardata"

CONF_CARDATA_DEVICE_ID: Final = "cardata_device_id"
DATA_COORDINATOR: Final = "coordinator"
PRESENTATION_SCHEMA_VERSION: Final = 1

CONF_LICENSE_PLATE: Final = "license_plate"
CONF_IMAGE: Final = "image"
CONF_IMAGE_ENABLED: Final = "enabled"
CONF_IMAGE_PROVIDER: Final = "provider"
CONF_IMAGE_API_KEY: Final = "api_key"
CONF_IMAGE_MODEL: Final = "model"
CONF_IMAGE_SIZE: Final = "size"
CONF_IMAGE_VIEW_MODE: Final = "view_mode"
CONF_IMAGE_SCENE_MODE: Final = "scene_mode"

SERVICE_REFRESH: Final = "refresh"
SERVICE_REGENERATE_IMAGES: Final = "regenerate_images"
SERVICE_CLEAR_IMAGE_CACHE: Final = "clear_image_cache"